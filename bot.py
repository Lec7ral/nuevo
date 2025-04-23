from flask import Flask, request, render_template, url_for, send_file
import asyncio
import telebot
import os, shutil, zipfile, glob, re
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
ABSOLUTE_PATH = os.getcwd()
miBot = telebot.TeleBot(BOT_API)
miBot.remove_webhook()
miBot.set_webhook(url=url)

# Variables globales
MAX_RUNNING_SCRIPTS = 6
active_scripts_count = 0
processes = {}  # Procesos activos
processes_list = {}  # Scripts disponibles
available_scripts = []  # Lista de scripts disponibles
current_script_index = 0  # Índice del script actual


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
    miBot.send_message(message.chat.id, "Si funciona es la ostia")
@miBot.message_handler(commands=["enserio?"])
def cmd_enserio(message):
    miBot.reply_to(message, "Pos mira que si")




def create_process_buttons():
    """Crea botones para los procesos en ejecución."""
    keyboard = telebot.types.InlineKeyboardMarkup()
    for name in processes_list.keys():
        # Verifica si el proceso está en el diccionario de procesos
        if name in processes:
            # Verifica si el proceso está corriendo
            status = "🟢" if processes[name].poll() is None else "🔴"  # Verde si está corriendo, rojo si está detenido
        else:
            status = "🔴"  # Si no está en el diccionario, se considera detenido
        keyboard.add(telebot.types.InlineKeyboardButton(f"{status} {name}", callback_data=name))
    
    keyboard.add(telebot.types.InlineKeyboardButton("Agregar Proceso", callback_data="add_process"))
    return keyboard
@miBot.message_handler(commands=['list'])
def list_processes(message):
    """Muestra los procesos en ejecución con botones."""
    keyboard = create_process_buttons()
    miBot.send_message(message.chat.id, "Selecciona un proceso:", reply_markup=keyboard)
@miBot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    """Maneja las interacciones con los botones."""
    if call.data == "add_process":
        miBot.send_message(call.message.chat.id, "Proceso.")
        miBot.register_next_step_handler(call.message, add_process)
    elif call.data in processes:
        # Si el proceso está corriendo, lo detenemos; si no, lo iniciamos
        if processes[call.data].poll() is None:
            stop_process(call.data)    
        else:
            start_process(call.data)
    else:
        start_process(call.data)

    # Volver a mostrar los botones después de la acción
    keyboard = create_process_buttons()
    miBot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=keyboard)
    
def add_process(message):
    global available_scripts
    """Agrega un nuevo proceso a la lista."""
    try:
        #script_info = message.text.split(',')
        process_name = message.text.strip()
        #script_name = script_info[2].strip()  # Nombre del script
        #relative_path = script_info[1].strip()  # Ruta relativa del script


        # Construir la ruta completa del script
        full_script_path = os.path.join(ABSOLUTE_PATH, process_name, "meomundep.js")
        absolute_file_path = os.path.join(ABSOLUTE_PATH, process_name)

        # Verificar si el script existe
        if not os.path.isfile(full_script_path):
            miBot.send_message(message.chat.id, f"Error: El script '{full_script_path}' no existe.")
            return

        # Iniciar el proceso
        threading.Thread(target=run_process, args=(absolute_file_path, process_name, "meomundep.js")).start()
        miBot.send_message(message.chat.id, f"Proceso '{process_name}' agregado y en ejecución.")
        processes_list[process_name] = {
            'script' : "meomundep.js",
            'route' : absolute_file_path
        }
        available_scripts = list(processes_list.keys())
    except Exception as e:
        miBot.send_message(message.chat.id, f"Error al agregar el proceso: {e}")


@miBot.message_handler(commands=["inst"])
def cmd_install(message):
    res =  install_node_env()
    miBot.reply_to(message, "instalado")
    miBot.reply_to(message, f"{res}")
    try:
        res =  create_node_env()
        miBot.reply_to(message, f"{res}")
        miBot.reply_to(message, "Creado el entorno")
    except:
        miBot.send_message(message.chat.id, "Error")
    try:
        res =  activate_node_env()
        miBot.reply_to(message, "Activado")
        miBot.reply_to(message, f"{res}")
    except:
        miBot.send_message(message.chat.id, "Error")
    res =  install_modules()
    miBot.reply_to(message, "Modulos instalados")
    miBot.reply_to(message, f"{res}")



@miBot.message_handler(commands=["modules"])
def cmd_modules(message):
    modules_to_install = message.text.split()[1:]  # Ignora el primer elemento que es el comando
    if not modules_to_install:
        miBot.reply_to(message, "Por favor, proporciona los módulos a instalar.")
        return
    
    res = install_extra_modules(modules_to_install)
    miBot.reply_to(message, "Instalando módulos...")
    miBot.reply_to(message, f"{res}")



@miBot.message_handler(commands=["help"])
def cmd_help(message):
    help_text = (
        "/start - Iniciar el bot\n"
        "/enserio? - Respuesta divertida\n"
        "/inst - Instalar el entorno de Node.js\n"
        "/modules - Instalar módulos de Node.js\n"
        "/ls - Listar archivos y carpetas\n"
        "/mkdir <nombre> - Crear una carpeta\n"
        "/cd <nombre> - Cambiar de directorio\n"
        "/rm <nombre> - Eliminar un archivo o carpeta\n"
        "/mv <origen> <destino> - Mover un archivo o carpeta\n"
        "/zip <carpeta> - Comprimir una carpeta\n"
        "/unzip <carpeta> - Descomprimir una carpeta\n"
        "/up <nombre> - Subir archivo al chat\n"
        "/run <archivo.js> <nombre> - Ejecutar un script de Node.js\n"
        "/act - Listar procesos activos\n"
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
        folder_name = message.text[6:].strip()
        os.makedirs(folder_name)
        miBot.reply_to(message, f"Carpeta '{folder_name}' creada.")
    except IndexError:
        miBot.reply_to(message, "Por favor, proporciona un nombre para la carpeta.")
    except Exception as e:
        miBot.reply_to(message, f"Error: {str(e)}")

@miBot.message_handler(commands=["cd"])
def cmd_cd(message):
    try:
        dir_name = message.text[3:].strip()
        os.chdir(dir_name)  # Cambiar al directorio especificado
        miBot.reply_to(message, f"Cambiado a directorio '{dir_name}'.")

        # Obtener el listado actual de carpetas y archivos en el directorio
        current_directory = os.getcwd()  # Obtener el directorio actual
        items = os.listdir(current_directory)  # Listar archivos y carpetas

        # Crear un mensaje con el listado
        if items:
            items_list = "\n".join(items)  # Unir los nombres en una cadena
            miBot.reply_to(message, f"Contenido del directorio '{current_directory}':\n{items_list}")
        else:
            miBot.reply_to(message, f"El directorio '{current_directory}' está vacío.")

    except IndexError:
        miBot.reply_to(message, "Por favor, proporciona un nombre de directorio.")
    except FileNotFoundError:
        miBot.reply_to(message, "Directorio no encontrado.")
    except Exception as e:
        miBot.reply_to(message, f"Error: {str(e)}")

@miBot.message_handler(commands=["rm"])
def cmd_rm(message):
    try:
        item_name = message.text[3:].strip()
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

@miBot.message_handler(commands=["mv"])
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
        folder_name = message.text[4:].strip()
        shutil.make_archive(folder_name, 'zip', folder_name)
        miBot.reply_to(message, f"Carpeta '{folder_name}' comprimida en '{folder_name}.zip'.")
    except IndexError:
        miBot.reply_to(message, "Por favor, proporciona el nombre de la carpeta a comprimir.")
    except Exception as e:
        miBot.reply_to(message, f"Error: {str(e)}")

@miBot.message_handler(commands=["unzip"])
def cmd_unzip(message):
    try:
        zip_file = message.text[6:].strip()
        shutil.unpack_archive(zip_file, zip_file.replace('.zip', ''))
        miBot.reply_to(message, f"Archivo '{zip_file}' descomprimido.")
    except IndexError:
        miBot.reply_to(message, "Por favor, proporciona el nombre del archivo ZIP a descomprimir.")
    except Exception as e:
        miBot.reply_to(message, f"Error: {str(e)}")

@miBot.message_handler(commands=["del"])
def handle_del_process(message):
    global available_scripts
    try:
        to_del = message.text[4:].strip()
        del processes_list[to_del]
        available_scripts = list(processes_list.keys())
        miBot.send_message(message.chat.id, f"Proceso {to_del} eliminado")
    except Exception as e:
            miBot.reply_to(message, f"Error al eliminar el proceso: {str(e)}")
        
        

@miBot.message_handler(content_types=['document'])
def handle_document(message):
    file_info = miBot.get_file(message.document.file_id)
    downloaded_file = miBot.download_file(file_info.file_path)
    
    # Guardar el archivo recibido
    with open(message.document.file_name, 'wb') as new_file:
        new_file.write(downloaded_file)
    
    miBot.reply_to(message, f"Archivo '{message.document.file_name}' recibido y guardado.")
    
    # Verificar si el archivo es un .zip
    if message.document.file_name.endswith('.zip'):
        try:
            # Descomprimir el archivo .zip
            zip_file = message.document.file_name
            shutil.unpack_archive(zip_file, zip_file.replace('.zip', ''))  # Extraer en una carpeta con el mismo nombre sin .zip
            
            # Eliminar el archivo .zip
            os.remove(zip_file)
            miBot.reply_to(message, f"Archivo '{zip_file}' descomprimido y eliminado.")
        except IndexError:
            miBot.reply_to(message, "Por favor, proporciona el nombre del archivo ZIP a descomprimir.")
        except Exception as e:
            miBot.reply_to(message, f"Error al descomprimir el archivo: {str(e)}")

@miBot.message_handler(commands=["up"])
def cmd_sendfile(message):
    try:
        file_name = message.text[7:].strip()
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
        process_name = message.text.split()[1]
        start_process(process_name)
        miBot.reply_to(message, "Paso por aqui, se debe estar ejecutando")
    except Exception as e:
        miBot.reply_to(message, f"Error: {str(e)}")

@miBot.message_handler(commands=["act"])
def cmd_processes_activ(message):
    dict_as_string = str(processes_list)
    miBot.reply_to(message, dict_as_string)
    """Lista todos los subprocesos en ejecución y envía la información al chat de Telegram."""
    if not processes:
        miBot.send_message(message.chat.id, "No hay subprocesos en ejecución.")
    else:
        message_text = "Subprocesos en ejecución:\n"
        for name in list(processes.keys()):
            process = processes[name]
            if process.poll() is None:  # Si el proceso sigue en ejecución
                message_text += f"- {name} (PID: {process.pid})\n"
            else:
                message_text += f"- {name} ha terminado.\n"
                del processes[name]  # Eliminar el proceso terminado
        miBot.send_message(message.chat.id, message_text)
        miBot.send_message(message.chat.id, active_scripts_count)


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
def install_extra_modules(modules):
    result = subprocess.run(['npm', 'i'] + modules, capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else result.stderr
    
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

def run_process(route, name, file_js):
    global active_scripts_count
    """Inicia un proceso y lo almacena en el diccionario, leyendo la salida en tiempo real."""
    try:
        os.chdir(route)
        # Iniciar el proceso y redirigir la salida
        process = subprocess.Popen(['node', file_js], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        processes[name] = process
        print(f"Proceso '{name}' iniciado.")
        active_scripts_count += 1

        # Leer la salida y errores en tiempo real
        while True:
            output = process.stdout.readline()  # Leer una línea de la salida estándar
            if output == '' and process.poll() is not None:
                break  # Salir si el proceso ha terminado
            if output:
                print(output.strip())  # Imprimir la salida
                if "Waiting" in output:
                    print(f"'{name}' está en espera. Deteniendo el proceso.")
                    stop_process(name)
                    # Iniciar el siguiente script
                    start_next_script()
                try:
                    if re.search(r'login', output, re.IGNORECASE) and re.search(r'failed', output, re.IGNORECASE):
                        print(f"'{name}' ha fallado en el login. Deteniendo el proceso.")
                        stop_process(name)
                        miBot.send_message(971580959, f"Error de inicio de sesión en '{name}'.")  # Enviar mensaje al chat
                        start_next_script()
                except Exception as e:
                    print(e)
                    
        # Leer la salida de error
        stderr_output = process.stderr.read()
        if stderr_output:
            print("Error de salida:", stderr_output.strip())  # Imprimir errores

    except Exception as e:
        print(f"Se produjo un error: {e}")
    finally:
        with threading.Lock():
            active_scripts_count -= 1

def start_next_script():
    global active_scripts_count, current_script_index
    while active_scripts_count < MAX_RUNNING_SCRIPTS:
        # Asegúrate de que el índice esté dentro de los límites
        if current_script_index >= len(available_scripts):
            current_script_index = 0  # Reiniciar el índice si es necesario

        # Lógica para seleccionar el siguiente script
        next_script_name = available_scripts[current_script_index]

        # Verificar si el script ya está en ejecución
        if next_script_name not in processes:
            next_script_info = processes_list[next_script_name]
            next_script_route = next_script_info['route']
            next_script_file = next_script_info['script']
            print(f"Iniciando el siguiente script: {next_script_name}")
            threading.Thread(target=run_process, args=(next_script_route, next_script_name, next_script_file)).start()
            current_script_index += 1  # Incrementar el índice para el siguiente script
            return  # Salir de la función después de iniciar un script

        # Si el script ya está en ejecución, simplemente incrementar el índice
        current_script_index += 1
# Ejecutar el proceso en un hilo separado
        
def start_process(name):
  if active_scripts_count < MAX_RUNNING_SCRIPTS:
    try:
        process_info = processes_list[name]
        script_name = process_info['script']
        script_route = process_info['route']
        threading.Thread(target=run_process, args=(script_route, name, script_name)).start()
    except Exception as e:
        print(e)
  else:
        print("Límite de scripts en ejecución alcanzado. Esperando para iniciar el script.")
      
def stop_process(name):
    """Detiene un proceso específico."""
    if name in processes:
        try:
            processes[name].terminate()  # Intenta terminar el proceso de manera ordenada
            processes[name].wait(timeout=5)  # Espera hasta 5 segundos para que se detenga
            print(f"Proceso '{name}' detenido.")
        except subprocess.TimeoutExpired:
            print(f"El proceso '{name}' no se detuvo a tiempo. Forzando la terminación.")
            processes[name].kill()  # Forzar la terminación si no se detuvo
            print(f"Proceso '{name}' forzado a detenerse.")
        except Exception as e:
            print(f"Error al detener el proceso '{name}': {e}")
        finally:
            del processes[name]  # Elimina el proceso del diccionario
    else:
        print(f"No se encontró el proceso '{name}'.")

