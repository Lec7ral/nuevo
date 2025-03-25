from flask import Flask, request, render_template, url_for, send_file
import asyncio
import telebot
import os, shutil, zipfile, glob
from pathlib import Path
import asyncio, shlex
from typing import Tuple
import subprocess
import sys
import signal


BOT_API = os.environ['BOT_API']
secret = os.environ['SECRET']
url = 'https://nuevo-uf5s.onrender.com'

miBot = telebot.TeleBot(BOT_API, threaded = False)
miBot.remove_webhook()
miBot.set_webhook(url=url)

app = Flask(__name__)
@app.route('/', methods=['GET', 'POST'])
def webhook():
    if request.method == 'POST':
        update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
        miBot.process_new_updates([update])
        return 'ok', 200
    else:
        return 'Hello, World!'  # o cualquier otra respuesta para GET
        
@app.route('/files')
def list_files():
    files = os.listdir('.')
    files_with_links = []
    for file in files:
        file_path = os.path.join('.', file)
        if os.path.isdir(file_path):
            files_with_links.append((file + '/', url_for('navigate_folder', path=file_path)))
        else:
            files_with_links.append((file, url_for('serve_file', path=file_path)))
    return render_template('files.html', files=files_with_links, current_path='.')

@app.route('/files/download/<path:path>')
def serve_file(path):
    return send_file(path, as_attachment=True)

@app.route('/files/<path:path>')
def navigate_folder(path):
    files = os.listdir(path)
    files_with_links = []
    for file in files:
        file_path = os.path.join(path, file)
        if os.path.isdir(file_path):
            files_with_links.append((file + '/', url_for('navigate_folder', path=file_path)))
        else:
            files_with_links.append((file, url_for('serve_file', path=file_path)))
    return render_template('files.html', files=files_with_links, current_path=path)
    
if __name__ == '__main__':
    app.run(debug=True)
@miBot.message_handler(commands=["start"])
def cmd_start(message):
    miBot.reply_to(message, "Si funciona es la ostia")
@miBot.message_handler(commands=["enserio?"])
def cmd_enserio(message):
    miBot.reply_to(message, "Pos mira que si")








@miBot.message_handler(commands=["inst"])
def cmd_install(message):
    res =  install_node_env()
    miBot.reply_to(message, "algo hizo")
    miBot.reply_to(message, f"{res}")

@miBot.message_handler(commands=["create"])
def cmd_create(message):
    res =  create_node_env()
    miBot.reply_to(message, "algo hizo")
    miBot.reply_to(message, f"{res}")

@miBot.message_handler(commands=["act"])
def cmd_install(message):
    res =  activate_node_env()
    miBot.reply_to(message, "algo hizo")
    miBot.reply_to(message, f"{res}")

@miBot.message_handler(commands=["modules"])
def cmd_install(message):
    res =  install_modules()
    miBot.reply_to(message, "algo hizo")
    miBot.reply_to(message, f"{res}")







@miBot.message_handler(content_types=['text'])
def download(message):
   # if message.from_user.id!= Config.OWNER_ID: para que solo el due;o del miBot
    #    return
    url = message.text


def install_node_env():
   install =  subprocess.run(['pip', 'install', 'nodeenv'], check=True)
   return install

def create_node_env():
    # Crear un entorno de Node.js con la versión específica
    create =  subprocess.run(['nodeenv', 'nenv', '--node=22.11.0'], check=True)
    return create

def activate_node_env():
    # Activar el entorno de Node.js
    activate_script =  os.path.join('nenv', 'bin', 'activate')  # Linux/Mac
    activate =  subprocess.run(activate_script, shell=True, check=True)
    # activate_script = os.path.join(env_name, 'Scripts', 'activate')  # Windows
    return activate
def install_modules():
    modules =  subprocess.run(['npm', 'i', 'user-agents', 'cloudscraper', 'axios', 'colors', 'p-limit', 'https-proxy-agent', 'socks-proxy-agent', 'crypto', 'ws', 'qs'])
    return modules



