from app import app
from flask import render_template

@app.route('/')
@app.route('/index')
def index():
    return render_template('index.html', title='Home')

@app.route('/crop')
def crop():
    return render_template('crop.html', title='Crop Paper')