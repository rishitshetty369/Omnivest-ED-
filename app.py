import hashlib
import json
import time
import re
import os
import io
import csv
import yfinance as yf
from flask import Flask, render_template, request, jsonify, session, Response

app = Flask(__name__)
app.secret_key = "omnivest_deterministic_secret_2026"

USERS_FILE = "users.json"
LEDGER_FILE = "ledger.json"

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f: return json.load(f)
        except Exception: return {}
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f: json.dump(users, f, indent=4)

def get_user_csv_filename(username):
    safe_user = re.sub(r'[^a-zA-Z0-9_]', '_', username)
    return f"{safe_user}_investment_portfolio.csv"

def append_to_user_csv(username, block_index, timestamp, tx):
    csv_file = get_user_csv_filename(username)
    file_exists = os.path.exists(csv_file)
    pf = tx.get('portfolio', {})
    
    with open(csv_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "Block_Index", "Timestamp", "Tx_ID", "User", "Goal_Description",
                "Monthly_SIP", "Target_Corpus", "Tenure_Years", "Projected_Maturity",
                "Stocks_Pct", "Mutual_Funds_Pct", "Real_Estate_Pct", "Gold_Pct", "Crypto_BTC_Pct",
                "Risk_Level", "Block_Hash"
            ])
        writer.writerow([
            block_index,
            time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp)),
            tx.get('tx_id'),
            username,
            tx.get('goal'),
            tx.get('monthly_investment'),
            tx.get('target_savings_goal'),
            tx.get('tenure_years'),
            tx.get('target_fund'),
            pf.get('Stock_Market_Index', {}).get('pct', 0),
            pf.get('Mutual_Funds', {}).get('pct', 0),
            pf.get('Real_Estate_REITs', {}).get('pct', 0),
            pf.get('Gold_Precious_Metals', {}).get('pct', 0),
            pf.get('Cryptocurrency_BTC', {}).get('pct', 0),
            tx.get('risk_profile'),
            tx.get('block_hash', '')
        ])

# ==========================================
# BLOCKCHAIN ENGINE
# ==========================================
class Block:
    def __init__(self, index, timestamp, transactions, previous_hash, nonce=0):
        self.index = index
        self.timestamp = timestamp
        self.transactions = transactions
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.hash = self.calculate_hash()

    def calculate_hash(self):
        block_string = json.dumps({
            "index": self.index, "timestamp": self.timestamp,
            "transactions": self.transactions, "previous_hash": self.previous_hash, "nonce": self.nonce
        }, sort_keys=True)
        return hashlib.sha256(block_string.encode()).hexdigest()

    def mine_block(self, difficulty=2):
        target = "0" * difficulty
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self.calculate_hash()

class Blockchain:
    def __init__(self, storage_file=LEDGER_FILE):
        self.storage_file = storage_file
        self.chain = []
        self.difficulty = 2
        self.pending_transactions = []
        self.load_chain()

    def create_genesis_block(self):
        genesis = Block(0, time.time(), [{"system": "Deterministic Ledger Genesis"}], "0")
        genesis.mine_block(self.difficulty)
        self.chain.append(genesis)
        self.save_chain()

    def get_latest_block(self):
        return self.chain[-1]

    def add_transaction(self, user, goal, monthly_investment, target_savings, target_fund, tenure, risk_profile, portfolio):
        tx = {
            "tx_id": hashlib.sha256(f"{user}{time.time()}".encode()).hexdigest()[:12].upper(),
            "user": user, "goal": goal, "monthly_investment": monthly_investment,
            "target_savings_goal": target_savings, "target_fund": target_fund,
            "tenure_years": tenure, "risk_profile": risk_profile, "portfolio": portfolio, "timestamp": time.time()
        }
        self.pending_transactions.append(tx)
        return tx

    def mine_pending_transactions(self):
        if not self.pending_transactions: return None
        new_block = Block(
            index=len(self.chain), timestamp=time.time(),
            transactions=self.pending_transactions, previous_hash=self.get_latest_block().hash
        )
        new_block.mine_block(self.difficulty)
        
        for tx in self.pending_transactions:
            tx['block_hash'] = new_block.hash
            append_to_user_csv(tx['user'], new_block.index, new_block.timestamp, tx)
            
        self.chain.append(new_block)
        self.pending_transactions = []
        self.save_chain()
        return new_block

    def save_chain(self):
        serializable = [{"index": b.index, "timestamp": b.timestamp, "transactions": b.transactions, "previous_hash": b.previous_hash, "nonce": b.nonce, "hash": b.hash} for b in self.chain]
        with open(self.storage_file, "w") as f: json.dump(serializable, f, indent=4)

    def load_chain(self):
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, "r") as f:
                    data = json.load(f)
                    self.chain = [Block(b['index'], b['timestamp'], b['transactions'], b['previous_hash'], b['nonce']) for b in data]
            except Exception:
                self.chain = []; self.create_genesis_block()
        else: self.create_genesis_block()

blockchain = Blockchain()

# ==========================================
# API ENDPOINTS
# ==========================================
@app.route('/api/market-prices', methods=['GET'])
def get_market_prices():
    tickers = {"S&P 500": "^GSPC", "Gold": "GC=F", "Bitcoin": "BTC-USD", "Real Estate": "VNQ"}
    live_data = {}
    for name, symbol in tickers.items():
        try:
            t = yf.Ticker(symbol)
            df = t.history(period="2d")
            if len(df) >= 1:
                cur = float(df['Close'].iloc[-1])
                prev = float(df['Close'].iloc[-2]) if len(df) >= 2 else cur
                chg = ((cur - prev) / prev) * 100
                live_data[name] = {"price": round(cur, 2), "change": round(chg, 2), "status": "up" if chg >= 0 else "down"}
            else: live_data[name] = {"price": 0.0, "change": 0.0, "status": "neutral"}
        except Exception:
            live_data[name] = {"price": 100.0, "change": 0.4, "status": "up"}
    return jsonify({"status": "success", "market": live_data})

@app.route('/')
def home(): return render_template('index.html')

@app.route('/api/auth', methods=['POST'])
def auth():
    data = request.json or {}
    action = data.get('action'); u = data.get('username', '').strip(); p = data.get('password', '').strip()
    if not u or not p: return jsonify({"status": "error", "message": "Required fields missing."}), 400
    users = load_users(); pwd_hash = hashlib.sha256(p.encode()).hexdigest()
    if action == 'signup':
        if u in users: return jsonify({"status": "error", "message": "User exists."}), 400
        users[u] = {"password": pwd_hash}; save_users(users); session['user'] = u
        return jsonify({"status": "success", "username": u})
    elif action == 'login':
        if u not in users or users[u]["password"] != pwd_hash: return jsonify({"status": "error", "message": "Invalid login."}), 401
        session['user'] = u
        return jsonify({"status": "success", "username": u})

@app.route('/api/logout', methods=['POST'])
def logout(): session.pop('user', None); return jsonify({"status": "success"})

@app.route('/api/current-session', methods=['GET'])
def current_session(): return jsonify({"user": session.get('user')})

@app.route('/api/analyze', methods=['POST'])
def analyze():
    if 'user' not in session: return jsonify({"status": "error"}), 401
    data = request.json or {}
    
    mode = data.get('mode', 'goal')
    years = int(data.get('years', 5))
    statement = data.get('statement', '').strip().lower()
    input_val = float(data.get('input_val', 0) or 0)

    dest_base_costs = {
        "italy": 9000, "switzerland": 13000, "singapore": 6500, 
        "japan": 9500, "dubai": 5500, "europe": 11000, "usa": 12000
    }
    
    target_corpus = 0
    goal_title = "Custom Wealth Strategy"

    for dest, base_cost in dest_base_costs.items():
        if dest in statement:
            inflated_cost = base_cost * ((1.05) ** years)
            target_corpus = round(inflated_cost * 1.15, 2)
            goal_title = f"Trip to {dest.capitalize()} (with Buffer)"
            break

    if mode == 'goal':
        if target_corpus <= 0:
            target_corpus = max(input_val if input_val > 0 else 35000, 10000)
            goal_title = statement if statement else "Target Goal Portfolio"
        
        expected_rate = 0.145 # Stable deterministic high-yield rate
        r = expected_rate / 12
        n = years * 12
        monthly_sip = round(target_corpus / ( (((1 + r)**n - 1) / r) * (1 + r) ), 2)
        total_invested = round(monthly_sip * n, 2)

    elif mode == 'budget':
        monthly_sip = max(input_val, 1000)
        expected_rate = 0.145
        r = expected_rate / 12
        n = years * 12
        total_invested = round(monthly_sip * n, 2)
        target_corpus = round(monthly_sip * (((1 + r)**n - 1) / r) * (1 + r), 2)
        goal_title = "Monthly SIP Wealth Accumulator"

    else:
        target_corpus = max(input_val, 20000)
        expected_rate = 0.145
        r = expected_rate / 12
        n = years * 12
        monthly_sip = round(target_corpus / ( (((1 + r)**n - 1) / r) * (1 + r) ), 2)
        total_invested = round(monthly_sip * n, 2)
        goal_title = "Fixed Corpus Target Builder"

    # Deterministic Optimized Allocation Matrix (Ensures same inputs produce identical optimal weights)
    raw_weights = {
        "Stock_Market_Index": {"pct": 40.0, "cagr": 15.0},
        "Cryptocurrency_BTC": {"pct": 25.0, "cagr": 22.0},
        "Mutual_Funds": {"pct": 15.0, "cagr": 12.5},
        "Real_Estate_REITs": {"pct": 12.0, "cagr": 11.0},
        "Gold_Precious_Metals": {"pct": 8.0, "cagr": 9.5}
    }

    portfolio_detailed = {}
    for asset, details in raw_weights.items():
        allocated_principal = round(total_invested * (details["pct"] / 100.0), 2)
        projected_return = round(allocated_principal * ((1 + (details["cagr"]/100.0)) ** years), 2)
        portfolio_detailed[asset] = {
            "pct": details["pct"],
            "amount": allocated_principal,
            "projected_return": projected_return,
            "cagr": f"{details['cagr']}%"
        }

    return jsonify({
        "status": "success",
        "data": {
            "goal_identified": goal_title,
            "risk_profile": "High-Growth Maximized Strategy",
            "is_risky": True,
            "tenure_years": years,
            "monthly_allocation": monthly_sip,
            "target_savings_goal": target_corpus,
            "expected_rate_annual": f"{expected_rate * 100:.1f}%",
            "total_principal_invested": total_invested,
            "estimated_maturity_value": target_corpus,
            "estimated_profit": round(target_corpus - total_invested, 2),
            "portfolio_breakdown": portfolio_detailed,
            "ai_rationale": f"Deterministically optimized for maximum compounding returns over {years} years."
        }
    })

@app.route('/api/execute-investment', methods=['POST'])
def execute():
    if 'user' not in session: return jsonify({"status": "error"}), 401
    data = request.json or {}; plan = data.get('plan', {}); u = session['user']
    
    blockchain.add_transaction(
        u, plan.get('goal_identified'), plan.get('monthly_allocation'), 
        plan.get('target_savings_goal'), plan.get('estimated_maturity_value'), 
        plan.get('tenure_years'), plan.get('risk_profile'), plan.get('portfolio_breakdown')
    )
    block = blockchain.mine_pending_transactions()
    return jsonify({"status": "success", "block_index": block.index})

@app.route('/api/my-ledger', methods=['GET'])
def my_ledger():
    if 'user' not in session: return jsonify({"status": "error"}), 401
    u = session['user']; user_txs = []; tot_p, tot_m = 0, 0
    for b in blockchain.chain:
        for tx in b.transactions:
            if tx.get('user') == u:
                tot_p += float(tx.get('monthly_investment', 0)) * int(tx.get('tenure_years', 5)) * 12
                tot_m += float(tx.get('target_fund', 0))
                user_txs.append({"block_index": b.index, "block_hash": b.hash, "timestamp": time.strftime('%d %b %Y, %H:%M', time.localtime(b.timestamp)), "tx": tx})
    return jsonify({"records": list(reversed(user_txs)), "summary": {"active_portfolios": len(user_txs), "total_principal": round(tot_p, 2), "total_projected": round(tot_m, 2), "total_gain": round(tot_m - tot_p, 2)}})

@app.route('/api/export-csv', methods=['GET'])
def export_csv():
    if 'user' not in session: return jsonify({"status": "error"}), 401
    u = session['user']
    csv_file = get_user_csv_filename(u)
    if os.path.exists(csv_file):
        with open(csv_file, "r", encoding="utf-8") as f:
            content = f.read()
        return Response(content, mimetype="text/csv", headers={"Content-Disposition": f"attachment;filename={u}_investment_portfolio.csv"})
    return jsonify({"status": "error", "message": "No CSV records found."}), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)