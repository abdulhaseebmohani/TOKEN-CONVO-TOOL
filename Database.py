# database.py
import os
import json
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Task(db.Model):
    id = db.Column(db.String(16), primary_key=True)
    task_name = db.Column(db.String(100))
    task_password = db.Column(db.String(100))
    prefix = db.Column(db.String(200))
    convo_id = db.Column(db.String(100))
    speed = db.Column(db.Integer)
    token_list = db.Column(db.Text)  # JSON as text
    message_list = db.Column(db.Text)  # JSON as text
    status = db.Column(db.String(20), default='running')
    start_time = db.Column(db.DateTime, default=datetime.now)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    def to_dict(self):
        return {
            'id': self.id,
            'task_name': self.task_name,
            'task_password': self.task_password,
            'prefix': self.prefix,
            'convo_id': self.convo_id,
            'speed': self.speed,
            'token_list': json.loads(self.token_list),
            'message_list': json.loads(self.message_list),
            'status': self.status,
            'start_time': self.start_time
        }
