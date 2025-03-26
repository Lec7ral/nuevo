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
import threading


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
def cmd_act(message):
    res =  activate_node_env()
    miBot.reply_to(message, "algo hizo")
    miBot.reply_to(message, f"{res}")

@miBot.message_handler(commands=["modules"])
def cmd_modules(message):
    res =  install_modules()
    miBot.reply_to(message, "algo hizo")
    miBot.reply_to(message, f"{res}")

@miBot.message_handler(commands=["change"])
def cmd_change(message):
    res, res1, res2 =  change_dir()
    miBot.reply_to(message, "algo hizo")
    miBot.reply_to(message, f"{res}")
    miBot.reply_to(message, f"{res1}")
    miBot.reply_to(message, f"{res2}")

@miBot.message_handler(commands=["help"])
def cmd_help(message):
    help_text = (
        "/start - Iniciar el bot\n"
        "/enserio? - Respuesta divertida\n"
        "/inst - Instalar el entorno de Node.js\n"
        "/create - Crear un entorno de Node.js\n"
        "/act - Activar el entorno de Node.js\n"
        "/modules - Instalar módulos de Node.js\n"
        "/change - Cambiar de directorio\n"
        "/ls - Listar archivos y carpetas\n"
        "/mkdir <nombre> - Crear una carpeta\n"
        "/cd <nombre> - Cambiar de directorio\n"
        "/rm <nombre> - Eliminar un archivo o carpeta\n"
        "/move <origen> <destino> - Mover un archivo o carpeta\n"
        "/zip <carpeta> - Comprimir una carpeta\n"
        "/unzip <carpeta> - Descomprimir una carpeta\n"
        "/upload <nombre> - Subir archivo al chat\n"
        "/run <archivo.js> <nombre> - Ejecutar un script de Node.js\n"
        "/activos - Listar procesos activos\n"
        "/stop <nombre> - Detener un proceso específico\n"
    )
    miBot.reply_to(message, help_text)

@miBot.message_handler(commands=["ls"])
def cmd_ls(message):
    files = os.listdir('.')
    response = "\n".join(files) if files else "No hay archivos o carpetas."
    miBot.reply_to(message, response)

@miBot.message_handler(commands=["mkdir"])
def cmd_mkdir(message):
    try:
        folder_name = message.text.split()[1]
        os.makedirs(folder_name)
        miBot.reply_to(message, f"Carpeta '{folder_name}' creada.")
    except IndexError:
        miBot.reply_to(message, "Por favor, proporciona un nombre para la carpeta.")
    except Exception as e:
        miBot.reply_to(message, f"Error: {str(e)}")

@miBot.message_handler(commands=["cd"])
def cmd_cd(message):
    try:
        dir_name = message.text.split()[1]
        os.chdir(dir_name)
        miBot.reply_to(message, f"Cambiado a directorio '{dir_name}'.")
    except IndexError:
        miBot.reply_to(message, "Por favor, proporciona un nombre de directorio.")
    except FileNotFoundError:
        miBot.reply_to(message, "Directorio no encontrado.")
    except Exception as e:
        miBot.reply_to(message, f"Error: {str(e)}")

@miBot.message_handler(commands=["rm"])
def cmd_rm(message):
    try:
        item_name = message.text.split()[1]
        if os.path.isdir(item_name):
            os.rmdir(item_name)  # Eliminar directorio vacío
            miBot.reply_to(message, f"Directorio '{item_name}' eliminado.")
        else:
            os.remove(item_name)  # Eliminar archivo
            miBot.reply_to(message, f"Archivo '{item_name}' eliminado.")
    except IndexError:
        miBot.reply_to(message, "Por favor, proporciona un nombre para eliminar.")
    except Exception as e:
        miBot.reply_to(message, f"Error: {str(e)}")

@miBot.message_handler(commands=["move"])
def cmd_move(message):
    try:
        args = message.text.split()
        if len(args) != 3:
            raise ValueError("Se requieren dos argumentos: origen y destino.")
        origen = args[1]
        destino = args[2]
        shutil.move(origen, destino)
        miBot.reply_to(message, f"Movido '{origen}' a '{destino}'.")
    except Exception as e:
        miBot.reply_to(message, f"Error: {str(e)}")

@miBot.message_handler(commands=["zip"])
def cmd_zip(message):
    try:
        folder_name = message.text.split()[1]
        shutil.make_archive(folder_name, 'zip', folder_name)
        miBot.reply_to(message, f"Carpeta '{folder_name}' comprimida en '{folder_name}.zip'.")
    except IndexError:
        miBot.reply_to(message, "Por favor, proporciona el nombre de la carpeta a comprimir.")
    except Exception as e:
        miBot.reply_to(message, f"Error: {str(e)}")

@miBot.message_handler(commands=["unzip"])
def cmd_unzip(message):
    try:
        zip_file = message.text.split()[1]
        shutil.unpack_archive(zip_file, zip_file.replace('.zip', ''))
        miBot.reply_to(message, f"Archivo '{zip_file}' descomprimido.")
    except IndexError:
        miBot.reply_to(message, "Por favor, proporciona el nombre del archivo ZIP a descomprimir.")
    except Exception as e:
        miBot.reply_to(message, f"Error: {str(e)}")

@miBot.message_handler(content_types=['document'])
def handle_document(message):
    file_info = miBot.get_file(message.document.file_id)
    downloaded_file = miBot.download_file(file_info.file_path)
    
    with open(message.document.file_name, 'wb') as new_file:
        new_file.write(downloaded_file)
    
    miBot.reply_to(message, f"Archivo '{message.document.file_name}' recibido y guardado.")

@miBot.message_handler(commands=["upload"])
def cmd_sendfile(message):
    try:
        file_name = message.text.split()[1]
        with open(file_name, 'rb') as file:
            miBot.send_document(message.chat.id, file)
    except IndexError:
        miBot.reply_to(message, "Por favor, proporciona el nombre del archivo a enviar.")
    except FileNotFoundError:
        miBot.reply_to(message, "Archivo no encontrado.")
    except Exception as e:
        miBot.reply_to(message, f"Error: {str(e)}")

@miBot.message_handler(commands=["run"])
def cmd_run_js(message):
    try:
        file_name = message.text.split()[1]
        process_name = message.text.split()[2]
        start_process(file_name, process_name)
        miBot.reply_to(message, "Paso por aqui, se debe estar ejecutando")
    except Exception as e:
        miBot.reply_to(message, f"Error: {str(e)}")

@miBot.message_handler(commands=["activos"])
def cmd_processes_activ(message):
    dict_as_string = str(processes)
    miBot.reply_to(message, dict_as_string)

@miBot.message_handler(commands=["stop"])
def vcmd_stop_js(message):
    try:
        file_name = message.text.split()[1]
        stop_process(file_name)
        miBot.reply_to(message, "Parece que lo detuvo")
    except Exception as e:
        miBot.reply_to(message, f"Error: {str(e)}")
        




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
def change_dir():
    present_directory = os.getcwd()
    change = os.chdir('..')
    after_dir = os.getcwd()
    return change, present_directory, after_dir

""" def run_node_script(script):
    process = subprocess.Popen(['node', script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    pid = process.pid
 """
# Diccionario para almacenar los procesos
processes = {}

def start_process(file_js, name):
    """Inicia un proceso y lo almacena en el diccionario."""
    process = subprocess.Popen(['node', file_js], shell=True)
    processes[name] = process
    print(f"Proceso '{name}' iniciado.")

def stop_process(name):
    """Detiene un proceso específico."""
    if name in processes:
        processes[name].terminate()  # O usa kill() si es necesario
        print(f"Proceso '{name}' detenido.")
        del processes[name]  # Elimina el proceso del diccionario
    else:
        print(f"No se encontró el proceso '{name}'.")

