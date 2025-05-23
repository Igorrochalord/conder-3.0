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
        'vencimento': vencimento_dt.astimezone(pytz.utc),  # Armazena em UTC
        'data_upload': datetime.utcnow(),
        'caminho': caminho
    }

    try:
        mongo.db.documentos.insert_one(documento)
        return jsonify({
            "msg": "Documento salvo com sucesso",
            "documento": nome_seguro
        }), 201
    except Exception as e:
        return jsonify({"msg": f"Erro ao salvar: {str(e)}"}), 500

@app.route('/api/grafico')
def grafico():
    try:
        # Usar data atual no timezone local como referência
        data_referencia = datetime.now(local_tz)
        meses_labels = []
        valores = []
        
        # Garantir que vamos pegar meses completos (do dia 1 ao último dia)
        primeiro_dia_mes_atual = data_referencia.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Gerar os 6 meses anteriores (incluindo o atual)
        periodos = []
        for i in range(6):
            mes = primeiro_dia_mes_atual - relativedelta(months=i)
            periodos.append({
                'inicio': mes,
                'fim': mes + relativedelta(months=1)
            })
        
        # Ordenar do mais antigo para o mais novo
        periodos.reverse()
        
        # Consultar o MongoDB para cada período
        for periodo in periodos:
            # Converter para UTC para a consulta
            inicio_utc = periodo['inicio'].astimezone(pytz.utc)
            fim_utc = periodo['fim'].astimezone(pytz.utc)
            
            total = mongo.db.documentos.count_documents({
                'data_upload': {
                    '$gte': inicio_utc,
                    '$lt': fim_utc
                }
            })
            
            # Formatar label (ex: "05/2023")
            label = periodo['inicio'].strftime('%m/%Y')
            meses_labels.append(label)
            valores.append(total)
        
        return jsonify({
            'labels': meses_labels,
            'valores': valores,
            'info': f"Dados de {meses_labels[0]} a {meses_labels[-1]}"
        })
    except Exception as e:
        app.logger.error(f"Erro ao gerar gráfico: {str(e)}", exc_info=True)
        return jsonify({'error': 'Erro ao processar dados do gráfico'}), 500

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
        
        return jsonify({'documentos': resultado})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/uploads/<path:nome>')
def servir_documento(nome):
    return send_from_directory(app.config["UPLOAD_FOLDER"], nome)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)