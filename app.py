from flask import Flask, jsonify, request
from flask_mysqldb import MySQL
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)

# Configuration MySQL
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')
app.config['MYSQL_PORT'] = int(os.getenv('MYSQL_PORT'))
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

mysql = MySQL(app)

# Route de test
@app.route('/test-db')
def test_db():
    cur = mysql.connection.cursor()
    cur.execute('SELECT DATABASE();')
    db_name = cur.fetchone()
    cur.close()
    return jsonify({"connexion": "réussie", "base": db_name[0]})

if __name__ == '__main__':
    app.run(debug=True)