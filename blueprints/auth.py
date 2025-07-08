from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user, login_user, logout_user
from werkzeug.security import check_password_hash

# Імпорти моделей та функцій
from models import User, db
from utils import log_user_activity

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.is_active and check_password_hash(user.password_hash, password):
            login_user(user)
            log_user_activity(user.id, 'Вхід до системи', request.remote_addr, request.url)
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Невірний логін або пароль, або обліковий запис заблоковано')
            
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    log_user_activity(current_user.id, 'Вихід із системи', request.remote_addr, request.url)
    logout_user()
    return redirect(url_for('index'))