from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from flask_pymongo import PyMongo
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os

app = Flask(__name__)
CORS(app)
bcrypt = Bcrypt(app)

app.config["MONGO_URI"] = "mongodb://localhost:27017/documentosdb"
app.config["UPLOAD_FOLDER"] = "uploads"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

mongo = PyMongo(app)
usuarios = mongo.db.usuarios
documentos = mongo.db.documentos

@app.route('/api/registro', methods=['POST'])
def registrar():
    dados = request.json
    if usuarios.find_one({'email': dados['email']}):
        return "Usuário já existe", 400
    senha_hash = bcrypt.generate_password_hash(dados['senha']).decode('utf-8')
    usuarios.insert_one({'email': dados['email'], 'senha': senha_hash})
    return "Registrado com sucesso"

@app.route('/api/login', methods=['POST'])
def login():
    dados = request.json
    user = usuarios.find_one({'email': dados['email']})
    if user and bcrypt.check_password_hash(user['senha'], dados['senha']):
        return "Login realizado"
    return "Credenciais inválidas", 401

@app.route('/api/documento', methods=['POST'])
def upload_documento():
    file = request.files['documento']
    tipo = request.form['tipo']
    vencimento = request.form['vencimento']
    nome_seguro = secure_filename(file.filename)
    caminho = os.path.join(app.config["UPLOAD_FOLDER"], nome_seguro)
    file.save(caminho)

    documentos.insert_one({
        'nome': nome_seguro,
        'tipo': tipo,
        'vencimento': datetime.strptime(vencimento, "%Y-%m-%d"),
        'data_upload': datetime.now()
    })
    return "Documento salvo com sucesso"

@app.route('/api/grafico')
def grafico():
    agora = datetime.now()
    meses = []
    valores = []
    for i in range(4):
        mes = (agora.replace(day=1) - timedelta(days=30*i)).strftime('%B/%Y')
        inicio_mes = agora.replace(day=1) - timedelta(days=30*i)
        fim_mes = inicio_mes.replace(day=28) + timedelta(days=4)
        fim_mes = fim_mes - timedelta(days=fim_mes.day)
        total = documentos.count_documents({
            'data_upload': {'$gte': inicio_mes, '$lt': fim_mes}
        })
        meses.insert(0, mes)
        valores.insert(0, total)
    return jsonify({'labels': meses, 'valores': valores})

@app.route('/uploads/<path:nome>')
def servir_documento(nome):
    return send_from_directory(app.config["UPLOAD_FOLDER"], nome)

if __name__ == '__main__':
    app.run(debug=True)
