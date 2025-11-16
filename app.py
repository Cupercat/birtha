from flask import Flask, request, jsonify
from models import db, User, Wallet
import requests
import jwt
import os
from auth import generate_token, token_required

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cryptoprice.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your_secret_key')

db.init_app(app)

COINS = ["bitcoin", "ethereum", "dogecoin"]
VS_CURRENCY = "usd"
COIN_URL = "https://api.coingecko.com/api/v3/simple/price"

with app.app_context():
    db.create_all()

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'message': 'User already exists'}), 400
    new_user = User(username=data['username'], password=data['password'])
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'message': 'User registered successfully'})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(username=data['username']).first()
    if not user or user.password != data['password']:
        return jsonify({'message': 'Invalid credentials'}), 401
    token = generate_token(user.id)
    return jsonify({'token': token})

@app.route('/balance', methods=['GET'])
@token_required
def get_balance(current_user_id):
    user = User.query.get(current_user_id)
    wallets = Wallet.query.filter_by(user_id=user.id).all()
    result = {}
    for w in wallets:
        result[w.coin_id] = w.amount
    return jsonify({'balance': result})

@app.route('/price', methods=['GET'])
def get_price():
    params = {
        "ids": ",".join(COINS),
        "vs_currencies": VS_CURRENCY,
        "include_24hr_change": "true"
    }
    response = requests.get(COIN_URL, params=params, timeout=10)
    return jsonify(response.json())

@app.route('/buy', methods=['POST'])
@token_required
def buy(current_user_id):
    data = request.json
    coin = data['coin']
    amount = float(data['amount'])
    price_response = requests.get(COIN_URL, params={
        "ids": coin,
        "vs_currencies": VS_CURRENCY
    })
    price_data = price_response.json()
    if coin not in price_data:
        return jsonify({'message': 'Invalid coin'}), 400
    price = price_data[coin][VS_CURRENCY]
    total_cost = price * amount

    user = User.query.get(current_user_id)
    if user.balance < total_cost:
        return jsonify({'message': 'Insufficient funds'}), 400

    user.balance -= total_cost
    wallet = Wallet.query.filter_by(user_id=user.id, coin_id=coin).first()
    if not wallet:
        wallet = Wallet(user_id=user.id, coin_id=coin, amount=amount)
        db.session.add(wallet)
    else:
        wallet.amount += amount

    db.session.commit()
    return jsonify({'message': f'Purchased {amount} {coin} for ${total_cost:.2f}'})

@app.route('/sell', methods=['POST'])
@token_required
def sell(current_user_id):
    data = request.json
    coin = data['coin']
    amount = float(data['amount'])

    wallet = Wallet.query.filter_by(user_id=current_user_id, coin_id=coin).first()
    if not wallet or wallet.amount < amount:
        return jsonify({'message': 'Not enough coins'}), 400

    price_response = requests.get(COIN_URL, params={
        "ids": coin,
        "vs_currencies": VS_CURRENCY
    })
    price_data = price_response.json()
    if coin not in price_data:
        return jsonify({'message': 'Invalid coin'}), 400
    price = price_data[coin][VS_CURRENCY]
    total_value = price * amount

    wallet.amount -= amount
    user = User.query.get(current_user_id)
    user.balance += total_value

    db.session.commit()
    return jsonify({'message': f'Sold {amount} {coin} for ${total_value:.2f}'})

if __name__ == '__main__':
    app.run(debug=True)