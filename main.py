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

class DispatchLinks(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    search_link = db.Column(db.String(1500), unique=True, nullable=False)
    search_term = db.Column(db.String(120), unique=True, nullable=False)

    def __repr__(self):
        return f'<DispatchLinks {self.search_link} - {self.search_term}>'

class FilterTerm(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filter_term = db.Column(db.String(120), unique=True, nullable=False)

    def __repr__(self):
        return f'<FilterTerm {self.filter_term}>'

class JobLocker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_title = db.Column(db.String(1500), unique=True, nullable=False)
    job_summary = db.Column(db.String(5000), nullable=False)
    job_published = db.Column(db.DateTime, nullable=False)
    job_search_term = db.Column(db.String(5000), nullable=False)
    job_price_type = db.Column(db.String(5000), nullable=False)

    def __repr__(self):
        return f'<JobLocker {self.job_title}>'

async def send_message_async(bot_token, group_chat_id, message):
    bot = Bot(token=bot_token)
    await bot.send_message(chat_id=group_chat_id, text=message, parse_mode='html')

def send_dispatch_telegram(title, summary, published_date, apply_link_match):
    max_message_length = 4096
    message = f"{published_date}\n\n{title}\n\n{summary}"
    
    if len(message) > max_message_length:
        parts = [message[i:i+max_message_length] for i in range(0, len(message), max_message_length)]
        for part in parts:
            asyncio.run(send_message_async(bot_token, '-1002131270840', part))
            time.sleep(1) 
    else:
        message += apply_link_match
        asyncio.run(send_message_async(bot_token, '-1002131270840', message))


def background_task():
    while True:
        print("Background task is running...")
        try:
            with app.app_context():
                links = DispatchLinks.query.all()
                filter_terms = FilterTerm.query.all()
                filter_term_list = [term.filter_term for term in filter_terms]
                
                for link in links:
                    feed_url = link.search_link
                    feed = feedparser.parse(feed_url)
                    if feed.bozo == 0:
                        for entry in feed.entries:
                            title = entry.title
                            summary = BeautifulSoup(entry.summary, 'html.parser').get_text()
                            published_date = date_parser.parse(entry.published)
                            job = JobLocker.query.filter_by(job_title=title).first()
                            apply_link_match = "H"
                            summary = entry.summary
                            tele_summary = (summary.replace('<br />', '\n'))
                            # print(apply_link_match)
                            if not job:
                                if any(term.lower() in summary.lower() for term in filter_term_list):
                                    print(f'New job found: {title}')
                                    send_dispatch_telegram(title, tele_summary, published_date, apply_link_match)
                                    # print(summary)
                                    for filter_term in filter_term_list:
                                        if filter_term.lower() in summary.lower():
                                            term = filter_term
                                            break
                                    budget_match = "H"
                                    price_type = None
                                    if budget_match:
                                        price_type = budget_match
                                    else:
                                        price_type = "Hourly"
                                    new_job = JobLocker(job_title=title, job_summary=summary, job_published=published_date, job_search_term = term, job_price_type = price_type)
                                    db.session.add(new_job)         
                                    db.session.commit()
                                    time.sleep(5)
        except Exception as e:
            print(f'Error: {e}')
            time.sleep(600)
        time.sleep(10)  # Run every 10 minutes


@app.route('/searchterm')
def index():
    links = DispatchLinks.query.all()
    return render_template('index.html', links=links)

@app.route('/')
def view_jobs():
    jobs = JobLocker.query.order_by(JobLocker.job_published.desc()).all()
    return render_template('view_jobs.html', jobs=jobs)

@app.route('/add', methods=['GET', 'POST'])
def add_link():
    if request.method == 'POST':
        link = request.form['link']
        search_term = request.form['search_term']
        new_link = DispatchLinks(search_link=link, search_term=search_term)
        try:
            db.session.add(new_link)
            db.session.commit()
            flash('Link added successfully!', 'success')
        except:
            db.session.rollback()
            flash('Error: The search term already exists or link is invalid!', 'danger')

        return redirect(url_for('add_link'))

    return render_template('add_link.html')


@app.route('/add_filter', methods=['GET', 'POST'])
def add_filter():
    if request.method == 'POST':
        filter_term = request.form['filter_term']
        new_filter = FilterTerm(filter_term=filter_term)

        try:
            db.session.add(new_filter)
            db.session.commit()
            flash('Filter term added successfully!', 'success')
        except:
            db.session.rollback()
            flash('Error: The filter term already exists or is invalid!', 'danger')
        return redirect(url_for('add_filter'))
    return render_template('add_filter.html')

@app.route('/view_filters')
def view_filters():
    filters = FilterTerm.query.all()
    return render_template('view_filters.html', filters=filters)


with app.app_context():
    db.create_all()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    thread = threading.Thread(target=background_task)
    thread.daemon = True
    thread.start()

    app.run(debug=True)
