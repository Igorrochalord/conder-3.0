from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_pymongo import PyMongo
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import pytz
import os

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# Configurações
app.config["MONGO_URI"] = os.getenv("MONGO_URI", "mongodb://localhost:27017/documentosdb")
app.config["UPLOAD_FOLDER"] = "uploads"
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Timezone do Brasil
local_tz = pytz.timezone('America/Sao_Paulo')

# Conexão com MongoDB
try:
    mongo = PyMongo(app)
    mongo.db.command('ping')
    print("✅ Conexão com MongoDB estabelecida!")
except Exception as e:
    print(f"❌ Erro ao conectar ao MongoDB: {e}")
    exit(1)

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/documento', methods=['POST'])
def upload_documento():
    if 'documento' not in request.files:
        return jsonify({"msg": "Nenhum arquivo enviado"}), 400
        
    file = request.files['documento']
    extensao = file.filename.split('.')[-1].lower()
    
    if not file or file.filename == '':
        return jsonify({"msg": "Nenhum arquivo selecionado"}), 400
    
    if '.' not in file.filename or extensao not in {'doc', 'docx', 'pdf'}:
        return jsonify({"msg": "Apenas arquivos .doc, .docx e .pdf são permitidos"}), 400

    nome_seguro = secure_filename(file.filename)
    caminho = os.path.join(app.config["UPLOAD_FOLDER"], nome_seguro)
    file.save(caminho)

    try:
        vencimento_dt = local_tz.localize(datetime.strptime(request.form['vencimento'], "%Y-%m-%d"))
    except Exception:
        return jsonify({"msg": "Data inválida. Use YYYY-MM-DD"}), 400

    documento = {
        'nome': nome_seguro,
        'tipo': request.form['tipo'],
        'extensao': extensao,
        'vencimento': vencimento_dt.astimezone(pytz.utc),
        'data_upload': vencimento_dt.astimezone(pytz.utc),  # Usando a data de vencimento como data de upload
        'caminho': caminho
    }

    try:
        mongo.db.documentos.insert_one(documento)
        return jsonify({
            "msg": "Documento salvo com sucesso",
            "documento": nome_seguro,
            "timestamp": datetime.now().isoformat()
        }), 201
    except Exception as e:
        return jsonify({"msg": f"Erro ao salvar: {str(e)}"}), 500

@app.route('/api/grafico')
def grafico():
    try:
        # Obter parâmetro de data de referência se existir
        data_ref_str = request.args.get('data_ref')
        if data_ref_str:
            try:
                data_ref = local_tz.localize(datetime.strptime(data_ref_str, "%Y-%m-%d"))
            except ValueError:
                return jsonify({"error": "Formato de data inválido. Use YYYY-MM-DD"}), 400
        else:
            data_ref = datetime.now(local_tz)
        
        meses_labels = []
        valores = []
        
        # Garantir 6 meses completos baseados na data de referência
        for i in range(5, -1, -1):  # 5 meses anteriores + atual
            mes = data_ref.replace(day=1) - relativedelta(months=i)
            inicio_mes = mes.replace(hour=0, minute=0, second=0, microsecond=0)
            fim_mes = (inicio_mes + relativedelta(months=1))
            
            total = mongo.db.documentos.count_documents({
                'data_upload': {
                    '$gte': inicio_mes.astimezone(pytz.utc),
                    '$lt': fim_mes.astimezone(pytz.utc)
                }
            })
            
            meses_labels.append(inicio_mes.strftime('%m/%Y'))
            valores.append(total)
        
        return jsonify({
            'labels': meses_labels,
            'valores': valores,
            'data_referencia': data_ref.strftime('%Y-%m-%d'),
            'status': 'success'
        })
    except Exception as e:
        app.logger.error(f"Erro no gráfico: {str(e)}")
        return jsonify({'error': str(e), 'status': 'error'}), 500

@app.route('/api/vencendo')
def documentos_a_vencer():
    try:
        hoje = datetime.utcnow().replace(tzinfo=pytz.utc)
        limite = hoje + timedelta(days=15)
        
        docs = mongo.db.documentos.find({
            'vencimento': {
                '$gte': hoje,
                '$lte': limite
            }
        }).sort('vencimento', 1)
        
        resultado = []
        for doc in docs:
            vencimento_local = doc['vencimento'].astimezone(local_tz)
            dias_restantes = (vencimento_local - datetime.now(local_tz)).days
            
            resultado.append({
                'nome': doc['nome'],
                'tipo': doc['tipo'],
                'extensao': doc.get('extensao', ''),
                'vencimento': vencimento_local.strftime('%d/%m/%Y'),
                'dias_restantes': dias_restantes
            })
        
        return jsonify({
            'documentos': resultado,
            'status': 'success'
        })
    except Exception as e:
        return jsonify({'error': str(e), 'status': 'error'}), 500

@app.route('/uploads/<path:nome>')
def servir_documento(nome):
    return send_from_directory(app.config["UPLOAD_FOLDER"], nome)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)