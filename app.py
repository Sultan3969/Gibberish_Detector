from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from detection import detect_gibberish
from correction import correct_text, manual_train
from voice import record_and_transcribe
import random
import os
import json
from datetime import datetime
from deep_translator import GoogleTranslator
import sqlite3
import io
from gtts import gTTS
from flask import send_file
import PyPDF2
import google.generativeai as genai

app = Flask(__name__)
app.secret_key = 'super_secret_capstone_key_do_not_share'

# Set up the live Gemini AI Chatbot and Grammar Corrector
api_key = os.environ.get("GEMINI_API_KEY", "AIzaSyBVA9G3gJJSQ3JLsO-oLYYD0pkwNPG2--0")
chat_histories = {}

if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        'gemini-2.5-flash',
        system_instruction="You are a helpful AI assistant for the 'Smart Gibberish Text Optimizer' application. You have access to a database context of the user's recent spelling/gibberish corrections. Answer the user's questions in a friendly, conversational manner. If they say hi, greet them. Do NOT just repeat or list the database context to them unless they explicitly ask about their past data, history, or mistakes."
    )
else:
    model = None

@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/send_otp', methods=['POST'])
def send_otp():
    otp = str(random.randint(100000, 999999))
    session['otp_code'] = otp
    session['pending_email'] = "administrator"
    
    print(f"\n=======================================================")
    print(f"SECURITY: Generated Server-Side Access Code: {otp}")
    print(f"=======================================================\n")
    
    return jsonify({
        'status': 'success', 
        'message': 'Code securely generated in terminal.'
    })

@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    entered_otp = data.get('code')
    
    if entered_otp and session.get('otp_code') == entered_otp:
        session['user'] = session.get('pending_email', 'authorized_user')
        session.pop('otp_code', None)
        session.pop('pending_email', None)
        return jsonify({'status': 'success', 'redirect': url_for('get_started')})
        
    return jsonify({'status': 'error', 'message': 'Invalid or expired code. Try again.'}), 400

@app.route('/get_started')
def get_started():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('get_started.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/save_result', methods=['POST'])
def save_result():
    data = request.get_json()
    if not data or 'original' not in data:
        return jsonify({'error': 'No data provided'}), 400
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO results (original, corrected, translated, label, timestamp) VALUES (?, ?, ?, ?, ?)',
                   (data.get('original'), data.get('corrected'), data.get('translated'), data.get('label'), timestamp))
    conn.commit()
    conn.close()
        
    return jsonify({'status': 'success', 'message': 'Result successfully saved to SQLite Database!'})

@app.route('/get_database', methods=['GET'])
def get_database():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT id, original, corrected, translated, label, timestamp FROM results ORDER BY id ASC')
    rows = cursor.fetchall()
    conn.close()
    
    records = []
    for row in rows:
        records.append({
            'id': row[0],
            'original': row[1],
            'corrected': row[2],
            'translated': row[3],
            'label': row[4],
            'timestamp': row[5]
        })
    return jsonify({'records': records})

@app.route('/delete_record', methods=['POST'])
def delete_record():
    data = request.get_json()
    record_id = data.get('id')
    if not record_id:
        return jsonify({'error': 'No ID provided'}), 400
        
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM results WHERE id = ?', (record_id,))
    conn.commit()
    conn.close()
    
    return jsonify({'status': 'success', 'message': 'Record deleted'})

@app.route('/tts', methods=['POST'])
def tts():
    data = request.get_json()
    text = data.get('text', '')
    lang = data.get('lang', 'en')
    
    if not text:
        return jsonify({'error': 'No text provided'}), 400
        
    try:
        # Fallback to English if gTTS throws an error on unsupported dialects, but generally these are supported.
        tts_obj = gTTS(text=text, lang=lang)
        mp3_fp = io.BytesIO()
        tts_obj.write_to_fp(mp3_fp)
        mp3_fp.seek(0)
        return send_file(mp3_fp, mimetype="audio/mp3")
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/process', methods=['POST'])
def process_text():
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({'error': 'No text provided'}), 400
        
    raw_input = data['text']
    input_text = raw_input
    target_lang = data.get('target', 'en')
    source_lang = data.get('source', 'en-US')
    
    if source_lang != 'en-US' and model:
        try:
            prompt = f"You are a raw text processor. Your ONLY job is to output the exact corrected version of the text below in its original language. Fix spelling, grammar, and gibberish. Maintain the exact same grammatical form (gender, tense, formality). Output absolutely nothing else. No conversational text, no greetings, no markdown, no quotes.\n\nTEXT:\n{raw_input}"
            corrected_native = model.generate_content(prompt).text.strip()
            
            corrected_text = GoogleTranslator(source='auto', target='en').translate(corrected_native)
            try:
                en_original = GoogleTranslator(source=source_lang.split('-')[0], target='en').translate(raw_input)
                label = detect_gibberish(en_original)
            except:
                label = detect_gibberish(corrected_text)

            src_short = source_lang.split('-')[0]
            if target_lang != 'en':
                if target_lang == src_short:
                    translated_text = corrected_native
                else:
                    translated_text = GoogleTranslator(source='auto', target=target_lang).translate(corrected_native)
            else:
                translated_text = ""
                
            return jsonify({
                'original': raw_input,
                'label': label,
                'corrected': corrected_text,
                'translated': translated_text
            })
        except Exception as e:
            pass

    # If the text is typed in a foreign language, translate it to English FIRST
    if source_lang != 'en-US':
        try:
            src_short = source_lang.split('-')[0]
            input_text = GoogleTranslator(source=src_short, target='en').translate(raw_input)
        except Exception as e:
            pass
            
    label = detect_gibberish(input_text)
    
    # Always attempt correction.
    corrected_text = correct_text(input_text)
    translated_text = ""
    
    if target_lang != 'en':
        text_to_translate = corrected_text if corrected_text else input_text
        if text_to_translate.strip() != "":
            try:
                translated_text = GoogleTranslator(source='en', target=target_lang).translate(text_to_translate)
            except Exception as e:
                pass
                
    if input_text.lower().strip() == corrected_text.lower().strip():
        if source_lang != 'en-US':
            corrected_text = input_text
        else:
            corrected_text = ""
        
    return jsonify({
        'original': raw_input,
        'label': label,
        'corrected': corrected_text,
        'translated': translated_text
    })

@app.route('/voice', methods=['POST'])
def process_voice():
    # Calling the local microphone to record and transcribe
    target_lang = request.form.get('target', 'en')
    source_lang = request.form.get('source', 'en-US')
    
    text, error = record_and_transcribe(source_lang)
    raw_text = text
    
    if error:
        return jsonify({'error': error}), 400
        
    if source_lang != 'en-US' and model:
        try:
            prompt = f"You are a raw text processor. Your ONLY job is to output the exact corrected version of the text below in its original language. Fix spelling, grammar, and gibberish. Maintain the exact same grammatical form (gender, tense, formality). Output absolutely nothing else. No conversational text, no greetings, no markdown, no quotes.\n\nTEXT:\n{raw_text}"
            corrected_native = model.generate_content(prompt).text.strip()
            
            corrected_text = GoogleTranslator(source='auto', target='en').translate(corrected_native)
            try:
                en_original = GoogleTranslator(source=source_lang.split('-')[0], target='en').translate(raw_text)
                label = detect_gibberish(en_original)
            except:
                label = detect_gibberish(corrected_text)

            src_short = source_lang.split('-')[0]
            if target_lang != 'en':
                if target_lang == src_short:
                    translated_text = corrected_native
                else:
                    translated_text = GoogleTranslator(source='auto', target=target_lang).translate(corrected_native)
            else:
                translated_text = ""
                
            return jsonify({
                'original': raw_text,
                'label': label,
                'corrected': corrected_text,
                'translated': translated_text
            })
        except Exception as e:
            pass
            
    # If spoken in a foreign language, translate it to English FIRST
    # so the English-based Gibberish Detector and Spellchecker can process it.
    if source_lang != 'en-US':
        try:
            # Extract just the language code (e.g., 'hi' from 'hi-IN') for better accuracy than 'auto'
            src_short = source_lang.split('-')[0]
            text = GoogleTranslator(source=src_short, target='en').translate(raw_text)
        except Exception as e:
            pass
            
    # Process the transcribed text
    label = detect_gibberish(text)
    
    corrected_text = correct_text(text)
    translated_text = ""
    
    if target_lang != 'en':
        text_to_translate = corrected_text if corrected_text else text
        if text_to_translate.strip() != "":
            try:
                translated_text = GoogleTranslator(source='en', target=target_lang).translate(text_to_translate)
            except Exception as e:
                pass

    if text.lower().strip() == corrected_text.lower().strip():
        if source_lang != 'en-US':
            corrected_text = text
        else:
            corrected_text = ""
        
    return jsonify({
        'original': raw_text,
        'label': label,
        'corrected': corrected_text,
        'translated': translated_text
    })

@app.route('/upload', methods=['POST'])
def process_upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
        
    text = ""
    if file.filename.endswith('.txt'):
        text = file.read().decode('utf-8', errors='ignore')
    elif file.filename.endswith('.pdf'):
        try:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
        except Exception as e:
            return jsonify({'error': f'Failed to parse PDF: {str(e)}'}), 500
    else:
        return jsonify({'error': 'Unsupported file type. Please upload .txt or .pdf'}), 400
        
    if not text.strip():
        return jsonify({'error': 'The uploaded file is empty or contains no readable text.'}), 400

    # User requested: optimized output only for English, no multilingual translation
    label = detect_gibberish(text)
    corrected_text = correct_text(text)
    
    if text.lower().strip() == corrected_text.lower().strip():
        corrected_text = ""
        
    return jsonify({
        'original': text,
        'label': label,
        'corrected': corrected_text,
        'translated': "" # Enforcing no multilingual translation for document upload
    })

@app.route('/train', methods=['POST'])
def train_model():
    data = request.get_json()
    if not data or 'bad_word' not in data or 'good_word' not in data:
        return jsonify({'error': 'Invalid data provided'}), 400
        
    manual_train(data['bad_word'], data['good_word'])
    return jsonify({'message': 'AI Model trained successfully!'})



@app.route('/chat', methods=['POST'])
def chatbot_response():
    global chat_histories
    data = request.get_json()
    query = data.get('query', '')
    
    if not model:
        return jsonify({'response': "Live chatbot is disabled. Please set the 'GEMINI_API_KEY' environment variable in your terminal and restart the app to enable the live AI assistant."})
        
    user = session.get('user', 'guest')
    if user not in chat_histories:
        chat_histories[user] = []
        
    chat_messages = chat_histories[user]
        
    # RAG - Database Augmented Generation
    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute('SELECT original, corrected, translated, label FROM results ORDER BY id DESC LIMIT 20')
        rows = cursor.fetchall()
        conn.close()
        
        db_context = ""
        if rows:
            for i, r in enumerate(rows):
                trans = r[2] if r[2] and r[2].strip() != "" else "None (English only)"
                db_context += f"{i+1}. Input: {r[0]} | Output: {r[1]} | Translated: {trans} | Status: {r[3]}\n"
        else:
            db_context = "No recent corrections in database yet."
            
        augmented_query = f"[SYSTEM INVISIBLE CONTEXT]\nRecent User Corrections Database:\n{db_context}\n[/SYSTEM INVISIBLE CONTEXT]\n\nUser's message: {query}"
        
        temp_history = chat_messages.copy()
        temp_history.append({'role': 'user', 'parts': [augmented_query]})
        
        response = model.generate_content(temp_history)
        
        chat_messages.append({'role': 'user', 'parts': [query]})
        chat_messages.append({'role': 'model', 'parts': [response.text]})
        
        # Keep history short to avoid context limits
        if len(chat_messages) > 10:
            chat_histories[user] = chat_messages[-10:]
        
        return jsonify({'response': response.text})
    except Exception as e:
        return jsonify({'response': f"An error occurred connecting to the live AI: {str(e)}"})

def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original TEXT,
            corrected TEXT,
            translated TEXT,
            label TEXT,
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()
    
    # Migrate JSON if exists
    if os.path.exists('database.json'):
        try:
            with open('database.json', 'r') as f:
                records = json.load(f)
                if records:
                    conn = sqlite3.connect('database.db')
                    cursor = conn.cursor()
                    for r in records:
                        cursor.execute('INSERT INTO results (original, corrected, translated, label, timestamp) VALUES (?, ?, ?, ?, ?)', 
                            (r.get('original'), r.get('corrected'), r.get('translated'), r.get('label'), r.get('timestamp')))
                    conn.commit()
                    conn.close()
            os.rename('database.json', 'database.json.bak')
        except:
            pass

if __name__ == '__main__':
    init_db()
    # Run the app locally
    app.run(debug=True, port=5000)
