from flask import Flask, request, render_template, flash, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import threading
import time
import feedparser
from dateutil import parser as date_parser
from datetime import datetime
import asyncio
from telegram import Bot
from bs4 import BeautifulSoup
import logging
import re

app = Flask(__name__)
app.secret_key = 'supersecretkey'

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


bot_token = '7162513284:AAGUXwYIhA19hFyj8dGV26Qh-TnSJci6soI'

class RSSFeedLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    search_link = db.Column(db.Text, nullable=False)
    search_term = db.Column(db.String(120), unique=True, nullable=False)

    def __repr__(self):
        return f'<RSSFeedLink {self.search_link} - {self.search_term}>'

class JobFilterTerm(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filter_term = db.Column(db.String(120), unique=True, nullable=False)

    def __repr__(self):
        return f'<JobFilterTerm {self.filter_term}>'

class JobListing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_title = db.Column(db.Text, nullable=False)
    job_summary = db.Column(db.Text, nullable=False)
    job_published = db.Column(db.DateTime, nullable=False)
    job_search_term = db.Column(db.String(5000), nullable=False)
    job_price_type = db.Column(db.String(5000), nullable=False)

    def __repr__(self):
        return f'<JobListing {self.job_title}>'

async def send_telegram_message_async(bot_token, group_chat_id, message):
    bot = Bot(token=bot_token)
    await bot.send_message(chat_id=group_chat_id, text=message, parse_mode='html')

def dispatch_job_to_telegram(title, summary, published_date, apply_link_match):
    max_message_length = 4096
    message = f"{published_date}\n\n{title}\n\n{summary}"
    
    if len(message) > max_message_length:
        parts = [message[i:i+max_message_length] for i in range(0, len(message), max_message_length)]
        for part in parts:
            asyncio.run(send_telegram_message_async(bot_token, '-1002131270840', part))
            time.sleep(1) 
    else:
        message += apply_link_match
        asyncio.run(send_telegram_message_async(bot_token, '-1002131270840', message))

def rss_feed_background_task():
    while True:
        # print("Background task is running...")
        try:
            with app.app_context():
                links = RSSFeedLink.query.all()
                filter_terms = JobFilterTerm.query.all()
                filter_term_list = [term.filter_term for term in filter_terms]
                
                for link in links:
                    feed_url = link.search_link
                    feed = feedparser.parse(feed_url)
                    if feed.bozo == 0:
                        for entry in feed.entries:
                            title = entry.title
                            summary_html = entry.summary
                            summary_text = BeautifulSoup(summary_html, 'html.parser').get_text()
                            published_date = date_parser.parse(entry.published)
                            job = JobListing.query.filter_by(job_title=title).first()
                            apply_link_match = "H"
                            
                            if not job:
                                if any(term.lower() in summary_text.lower() or term.lower() in title.lower() for term in filter_term_list):
                                    print(f'New job found: {title}')
                                    dispatch_job_to_telegram(title, summary_text.replace('<br />', '\n'), published_date, apply_link_match)
                                    new_job = JobListing(job_title=title, job_summary=summary_html, job_published=published_date, job_search_term=link.search_term, job_price_type="price_type")
                                    db.session.add(new_job)
                                    db.session.commit()
                                    time.sleep(5)
        except Exception as e:
            print(f'Error: {e}')
            time.sleep(60)
        time.sleep(10)


@app.route('/')
def display_jobs():
    jobs = JobListing.query.order_by(JobListing.job_published.desc()).all()
    return render_template('index.html', jobs=jobs)


@app.route('/delete_job/<int:job_id>', methods=['POST'])
def delete_job(job_id):
    job = JobListing.query.get_or_404(job_id)
    try:
        db.session.delete(job)
        db.session.commit()
        flash('Job deleted successfully!', 'success')
    except:
        db.session.rollback()
        flash('Error: Unable to delete job!', 'danger')
    return redirect(url_for('display_jobs'))


@app.route('/add_rss_feed_link', methods=['GET', 'POST'])
def add_rss_feed_link():
    if request.method == 'POST':
        link = request.form['link']
        search_term = request.form['search_term']
        new_link = RSSFeedLink(search_link=link, search_term=search_term)
        try:
            db.session.add(new_link)
            db.session.commit()
            flash('Link added successfully!', 'success')
        except:
            db.session.rollback()
            flash('Error: The search term already exists or link is invalid!', 'danger')

        return redirect(url_for('add_rss_feed_link'))

    return render_template('add_rss_feed_link.html')

@app.route('/view_rss_feed_links')
def view_rss_feed_links():
    links = RSSFeedLink.query.all()
    return render_template('view_rss_feed_links.html', links=links)

@app.route('/add_job_filter_term', methods=['GET', 'POST'])
def add_job_filter_term():
    if request.method == 'POST':
        filter_term = request.form['filter_term']
        new_filter = JobFilterTerm(filter_term=filter_term)

        try:
            db.session.add(new_filter)
            db.session.commit()
            flash('Filter term added successfully!', 'success')
        except:
            db.session.rollback()
            flash('Error: The filter term already exists or is invalid!', 'danger')
        return redirect(url_for('add_job_filter_term'))
    return render_template('add_job_filter_term.html')

@app.route('/view_job_filter_terms')
def view_job_filter_terms():
    filters = JobFilterTerm.query.all()
    return render_template('view_job_filter_terms.html', filters=filters)

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    thread = threading.Thread(target=rss_feed_background_task)
    thread.daemon = True
    thread.start()
    app.run(debug=True)
