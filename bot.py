import os
import threading
import subprocess
import shutil
import time
import logging
from pathlib import Path
from flask import Flask, request, render_template, url_for, send_file
import telebot

# Configuración inicial
BOT_API = os.environ['BOT_API']
SECRET = os.environ['SECRET']
URL = 'https://nuevo-uf5s.onrender.com'
ABSOLUTE_PATH = os.getcwd()

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Inicialización
app = Flask(__name__)
miBot = telebot.TeleBot(BOT_API, parse_mode=None)

# Configurar webhook al inicio
with app.app_context():
    miBot.remove_webhook()
    miBot.set_webhook(url=URL)
    logger.info("Webhook configurado")

# Diccionarios para gestión de procesos
processes = {}
processes_list = {}

# Variable global para seguimiento de estados
waiting_for_process_name = {}

# Rutas Flask
@app.route('/', methods=['GET', 'POST'])
def webhook():
    if request.method == 'POST':
        update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
        miBot.process_new_updates([update])
        return 'ok', 200
    else:
        return 'Hello, World!'

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

# Comandos básicos del bot
@miBot.message_handler(commands=["start"])
def cmd_start(message):
    miBot.send_message(message.chat.id, "✅ Bot funcionando correctamente")

@miBot.message_handler(commands=["enserio"])
def cmd_enserio(message):
    miBot.reply_to(message, "¡Pos mira que sí! 😄")

# Gestión de procesos con botones - VERSIÓN CORREGIDA
def create_process_buttons():
    """Crea botones para los procesos en ejecución."""
    keyboard = telebot.types.InlineKeyboardMarkup()
    
    current_time = int(time.time())
    
    for name in processes_list.keys():
        if name in processes:
            status = "🟢" if processes[name].poll() is None else "🔴"
        else:
            status = "🔴"
        
        keyboard.add(telebot.types.InlineKeyboardButton(
            f"{status} {name}", 
            callback_data=f"process_{name}_{current_time}"
        ))
    
    keyboard.add(telebot.types.InlineKeyboardButton(
        "➕ Agregar Proceso", 
        callback_data=f"add_process_{current_time}"
    ))
    
    return keyboard

@miBot.message_handler(commands=['list'])
def list_processes(message):
    """Muestra los procesos en ejecución con botones."""
    keyboard = create_process_buttons()
    miBot.send_message(message.chat.id, "🔧 **Gestión de Procesos:**", reply_markup=keyboard)

@miBot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    """Maneja las interacciones con los botones - VERSIÓN COMPLETAMENTE CORREGIDA"""
    try:
        logger.info(f"Callback recibido: {call.data}")
        
        # Extraer el tipo de acción y el nombre
        parts = call.data.split('_')
        action_type = parts[0]
        
        if action_type == "add":
            # CORRECCIÓN: Manejar agregar proceso
            miBot.answer_callback_query(call.id, "Por favor envía el nombre de la carpeta del proceso")
            
            # Marcar que estamos esperando el nombre del proceso
            waiting_for_process_name[call.message.chat.id] = True
            
            # Enviar mensaje separado para solicitar el nombre
            msg = miBot.send_message(
                call.message.chat.id, 
                "📝 **Agregar Nuevo Proceso**\n\nPor favor, envía el nombre de la carpeta donde está el script meomundep.js:",
                parse_mode='Markdown'
            )
            
            # Registrar el handler para el siguiente mensaje
            miBot.register_next_step_handler(msg, process_add_step)
            
        elif action_type == "process":
            # Manejar procesos existentes
            if len(parts) >= 2:
                process_name = parts[1]
                
                if process_name in processes and processes[process_name].poll() is None:
                    # Detener proceso
                    if stop_process(process_name):
                        miBot.answer_callback_query(call.id, f"⏹️ {process_name} detenido")
                    else:
                        miBot.answer_callback_query(call.id, f"❌ Error deteniendo {process_name}")
                else:
                    # Iniciar proceso
                    if start_process(process_name):
                        miBot.answer_callback_query(call.id, f"▶️ {process_name} iniciado")
                    else:
                        miBot.answer_callback_query(call.id, f"❌ Error iniciando {process_name}")
            
            # Actualizar la interfaz
            try:
                new_keyboard = create_process_buttons()
                miBot.edit_message_reply_markup(
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=new_keyboard
                )
            except Exception as e:
                if "message is not modified" not in str(e):
                    logger.warning(f"Error actualizando botones: {e}")

    except Exception as e:
        logger.error(f"Error en handle_query: {e}")
        miBot.answer_callback_query(call.id, "❌ Error procesando solicitud")

def process_add_step(message):
    """Procesa el nombre del nuevo proceso - VERSIÓN CORREGIDA"""
    try:
        chat_id = message.chat.id
        
        # Verificar si estamos esperando un nombre de proceso
        if chat_id not in waiting_for_process_name:
            return
            
        # Limpiar el estado
        del waiting_for_process_name[chat_id]
        
        process_name = message.text.strip()
        
        if not process_name:
            miBot.send_message(chat_id, "❌ El nombre del proceso no puede estar vacío.")
            return
        
        # Verificar si la carpeta existe
        folder_path = os.path.join(ABSOLUTE_PATH, process_name)
        if not os.path.exists(folder_path):
            miBot.send_message(chat_id, f"❌ La carpeta '{process_name}' no existe.")
            return
        
        # Verificar si el script existe
        script_path = os.path.join(folder_path, "meomundep.js")
        if not os.path.isfile(script_path):
            miBot.send_message(chat_id, f"❌ El script 'meomundep.js' no existe en la carpeta '{process_name}'.")
            return
        
        # Agregar a la lista de procesos
        processes_list[process_name] = {
            'script': "meomundep.js",
            'route': folder_path
        }
        
        # Iniciar el proceso
        if start_process(process_name):
            miBot.send_message(chat_id, f"✅ Proceso '{process_name}' agregado y en ejecución.")
        else:
            miBot.send_message(chat_id, f"⚠️ Proceso '{process_name}' agregado pero hubo un error al iniciarlo.")
        
        # Actualizar la lista de procesos
        try:
            keyboard = create_process_buttons()
            miBot.send_message(chat_id, "🔧 **Gestión de Procesos Actualizada:**", reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Error enviando teclado actualizado: {e}")
            
    except Exception as e:
        logger.error(f"Error en process_add_step: {e}")
        miBot.send_message(message.chat.id, f"❌ Error al agregar el proceso: {e}")

# Handler para mensajes de texto normales (evita conflictos)
@miBot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text_messages(message):
    """Maneja mensajes de texto que no son comandos"""
    chat_id = message.chat.id
    
    # Si no estamos esperando un nombre de proceso, ignorar
    if chat_id not in waiting_for_process_name:
        # Solo responder si no es un comando
        if not message.text.startswith('/'):
            miBot.send_message(chat_id, "Usa /help para ver los comandos disponibles.")
        return

# Comandos de instalación
@miBot.message_handler(commands=["inst"])
def cmd_install(message):
    """Instalación optimizada del entorno Node.js"""
    def install_task():
        try:
            steps = [
                ("🔧 Instalando nodeenv...", ['pip', 'install', 'nodeenv']),
                ("📦 Creando entorno Node.js...", ['nodeenv', 'nenv', '--node=22.11.0']),
                ("📚 Instalando módulos básicos...", ['npm', 'i', 'user-agents', 'cloudscraper', 
                                                    'axios', 'colors', 'p-limit', 'https-proxy-agent',
                                                    'socks-proxy-agent', 'ws', 'qs'])
            ]
            
            for step_name, command in steps:
                miBot.send_message(message.chat.id, step_name)
                result = subprocess.run(command, capture_output=True, text=True, cwd=ABSOLUTE_PATH)
                if result.returncode != 0:
                    miBot.send_message(message.chat.id, f"❌ Error en {step_name}:\n{result.stderr}")
                    return
            
            miBot.send_message(message.chat.id, "✅ Instalación completada")
            
        except Exception as e:
            miBot.send_message(message.chat.id, f"❌ Error en instalación: {e}")
    
    threading.Thread(target=install_task, daemon=True).start()
    miBot.reply_to(message, "🚀 Iniciando instalación... Esto puede tomar unos minutos.")

@miBot.message_handler(commands=["modules"])
def cmd_modules(message):
    """Instala módulos adicionales de Node.js"""
    modules_to_install = message.text.split()[1:]
    if not modules_to_install:
        miBot.reply_to(message, "📝 Uso: /modules <módulo1> <módulo2> ...")
        return
    
    def install_modules_task():
        try:
            miBot.send_message(message.chat.id, f"📦 Instalando: {', '.join(modules_to_install)}")
            result = subprocess.run(['npm', 'i'] + modules_to_install, 
                                 capture_output=True, text=True, cwd=ABSOLUTE_PATH)
            
            if result.returncode == 0:
                miBot.send_message(message.chat.id, "✅ Módulos instalados correctamente")
                if result.stdout:
                    output_preview = result.stdout[:1000] + "..." if len(result.stdout) > 1000 else result.stdout
                    miBot.send_message(message.chat.id, f"📄 Output:\n{output_preview}")
            else:
                miBot.send_message(message.chat.id, f"❌ Error:\n{result.stderr}")
                
        except Exception as e:
            miBot.send_message(message.chat.id, f"❌ Error instalando módulos: {e}")
    
    threading.Thread(target=install_modules_task, daemon=True).start()

# Comandos de sistema de archivos y procesos
@miBot.message_handler(commands=["help"])
def cmd_help(message):
    """Muestra ayuda"""
    help_text = """
/start - Iniciar el bot
/enserio - Respuesta divertida
/inst - Instalar el entorno de Node.js
/modules <módulos> - Instalar módulos de Node.js
/ls [ruta] - Listar archivos y carpetas
/mkdir <nombre> - Crear una carpeta
/cd <nombre> - Cambiar de directorio
/rm <nombre> - Eliminar un archivo o carpeta
/mv <origen> <destino> - Mover un archivo o carpeta
/zip <carpeta> - Comprimir una carpeta
/unzip <archivo> - Descomprimir un archivo
/up <nombre> - Subir archivo al chat
/run <nombre> - Ejecutar un script de Node.js
/act - Listar procesos activos
/stop <nombre> - Detener un proceso específico
/list - Gestión visual de procesos
"""
    miBot.reply_to(message, help_text, parse_mode=None)

@miBot.message_handler(commands=["ls"])
def cmd_ls(message):
    """Lista archivos y carpetas"""
    try:
        path = message.text[3:].strip() or '.'
        
        if not os.path.exists(path):
            miBot.reply_to(message, f"❌ Ruta no existe: {path}")
            return
        
        items = os.listdir(path)
        if not items:
            miBot.reply_to(message, f"📂 Directorio vacío: {path}")
            return
        
        def split_list(lst, chunk_size=20):
            for i in range(0, len(lst), chunk_size):
                yield lst[i:i + chunk_size]
        
        chunks = list(split_list(sorted(items)))
        
        for i, chunk in enumerate(chunks):
            response = f"📂 Página {i+1}/{len(chunks)} - {path}:\n\n"
            
            for item in chunk:
                item_path = os.path.join(path, item)
                icon = "📁" if os.path.isdir(item_path) else "📄"
                response += f"{icon} {item}\n"
            
            if i == 0:
                miBot.reply_to(message, response, parse_mode=None)
            else:
                miBot.send_message(message.chat.id, response, parse_mode=None)
                
    except Exception as e:
        miBot.reply_to(message, f"❌ Error: {str(e)}", parse_mode=None)

@miBot.message_handler(commands=["mkdir"])
def cmd_mkdir(message):
    try:
        folder_name = message.text[6:].strip()
        if not folder_name:
            miBot.reply_to(message, "📝 Uso: /mkdir <nombre_carpeta>")
            return
            
        os.makedirs(folder_name, exist_ok=True)
        miBot.reply_to(message, f"✅ Carpeta '{folder_name}' creada.")
    except Exception as e:
        miBot.reply_to(message, f"❌ Error: {str(e)}")

@miBot.message_handler(commands=["cd"])
def cmd_cd(message):
    try:
        dir_name = message.text[3:].strip()
        if not dir_name:
            miBot.reply_to(message, "📝 Uso: /cd <directorio>")
            return
            
        if not os.path.exists(dir_name):
            miBot.reply_to(message, f"❌ Directorio no existe: {dir_name}")
            return
            
        os.chdir(dir_name)
        current_directory = os.getcwd()
        items = os.listdir(current_directory)
        
        response = f"📂 Cambiado a directorio: {current_directory}\n\n"
        if items:
            response += "Contenido:\n" + "\n".join(items[:10])
            if len(items) > 10:
                response += f"\n... y {len(items) - 10} más"
        else:
            response += "El directorio está vacío."
            
        miBot.reply_to(message, response, parse_mode=None)
    except Exception as e:
        miBot.reply_to(message, f"❌ Error: {str(e)}")

@miBot.message_handler(commands=["rm"])
def cmd_rm(message):
    try:
        item_name = message.text[3:].strip()
        if not item_name:
            miBot.reply_to(message, "📝 Uso: /rm <nombre>")
            return
            
        if not os.path.exists(item_name):
            miBot.reply_to(message, f"❌ No existe: {item_name}")
            return
        
        if os.path.isdir(item_name):
            shutil.rmtree(item_name)
            miBot.reply_to(message, f"✅ Carpeta '{item_name}' eliminada.")
        else:
            os.remove(item_name)
            miBot.reply_to(message, f"✅ Archivo '{item_name}' eliminado.")
    except Exception as e:
        miBot.reply_to(message, f"❌ Error: {str(e)}")

@miBot.message_handler(commands=["mv"])
def cmd_move(message):
    try:
        args = message.text.split()
        if len(args) != 3:
            miBot.reply_to(message, "📝 Uso: /mv <origen> <destino>")
            return
            
        origen, destino = args[1], args[2]
        shutil.move(origen, destino)
        miBot.reply_to(message, f"✅ Movido '{origen}' a '{destino}'.")
    except Exception as e:
        miBot.reply_to(message, f"❌ Error: {str(e)}")

@miBot.message_handler(commands=["zip"])
def cmd_zip(message):
    try:
        folder_name = message.text[4:].strip()
        if not folder_name:
            miBot.reply_to(message, "📝 Uso: /zip <carpeta>")
            return
            
        if not os.path.exists(folder_name):
            miBot.reply_to(message, f"❌ Carpeta no existe: {folder_name}")
            return
        
        shutil.make_archive(folder_name, 'zip', folder_name)
        miBot.reply_to(message, f"✅ Comprimido: '{folder_name}.zip'.")
    except Exception as e:
        miBot.reply_to(message, f"❌ Error: {str(e)}")

@miBot.message_handler(commands=["unzip"])
def cmd_unzip(message):
    try:
        zip_file = message.text[6:].strip()
        if not zip_file:
            miBot.reply_to(message, "📝 Uso: /unzip <archivo.zip>")
            return
            
        if not os.path.exists(zip_file):
            miBot.reply_to(message, f"❌ Archivo no existe: {zip_file}")
            return
        
        extract_dir = zip_file.replace('.zip', '')
        shutil.unpack_archive(zip_file, extract_dir)
        miBot.reply_to(message, f"✅ Descomprimido: '{zip_file}' → '{extract_dir}'.")
    except Exception as e:
        miBot.reply_to(message, f"❌ Error: {str(e)}")

@miBot.message_handler(content_types=['document'])
def handle_document(message):
    """Procesa archivos subidos"""
    def process_document():
        try:
            file_info = miBot.get_file(message.document.file_id)
            downloaded_file = miBot.download_file(file_info.file_path)
            file_name = message.document.file_name
            
            with open(file_name, 'wb') as f:
                f.write(downloaded_file)
            
            if file_name.endswith('.zip'):
                extract_dir = file_name.replace('.zip', '')
                shutil.unpack_archive(file_name, extract_dir)
                os.remove(file_name)
                miBot.send_message(message.chat.id, f"✅ ZIP descomprimido: '{extract_dir}'")
            else:
                miBot.send_message(message.chat.id, f"✅ Archivo guardado: '{file_name}'")
                
        except Exception as e:
            miBot.send_message(message.chat.id, f"❌ Error procesando archivo: {e}")
    
    threading.Thread(target=process_document, daemon=True).start()
    miBot.reply_to(message, "📤 Procesando archivo...")

@miBot.message_handler(commands=["up"])
def cmd_sendfile(message):
    try:
        file_name = message.text[3:].strip()
        if not file_name:
            miBot.reply_to(message, "📝 Uso: /up <archivo>")
            return
            
        if not os.path.exists(file_name):
            miBot.reply_to(message, f"❌ Archivo no existe: {file_name}")
            return
        
        with open(file_name, 'rb') as file:
            miBot.send_document(message.chat.id, file)
    except Exception as e:
        miBot.reply_to(message, f"❌ Error: {str(e)}")

@miBot.message_handler(commands=["run"])
def cmd_run_js(message):
    try:
        args = message.text.split()
        if len(args) < 2:
            miBot.reply_to(message, "📝 Uso: /run <nombre_proceso>")
            return
            
        process_name = args[1]
        if start_process(process_name):
            miBot.reply_to(message, f"🚀 Proceso '{process_name}' iniciado")
        else:
            miBot.reply_to(message, f"❌ Error iniciando proceso '{process_name}'")
    except Exception as e:
        miBot.reply_to(message, f"❌ Error: {str(e)}")

@miBot.message_handler(commands=["act"])
def cmd_processes_activ(message):
    """Lista procesos activos"""
    if not processes:
        miBot.reply_to(message, "📭 No hay procesos en ejecución")
        return
    
    message_text = "🟢 Procesos Activos:\n"
    for name, process in list(processes.items()):
        if process.poll() is None:
            message_text += f"• {name}: 🟢 Ejecutándose (PID: {process.pid})\n"
        else:
            message_text += f"• {name}: 🔴 Terminado\n"
            del processes[name]
    
    miBot.reply_to(message, message_text, parse_mode=None)

@miBot.message_handler(commands=["stop"])
def cmd_stop_js(message):
    try:
        args = message.text.split()
        if len(args) < 2:
            miBot.reply_to(message, "📝 Uso: /stop <nombre_proceso>")
            return
            
        process_name = args[1]
        if stop_process(process_name):
            miBot.reply_to(message, f"⏹️ Proceso '{process_name}' detenido")
        else:
            miBot.reply_to(message, f"❌ Proceso '{process_name}' no encontrado")
    except Exception as e:
        miBot.reply_to(message, f"❌ Error: {str(e)}")

# Funciones de procesos
def run_process(route, name, file_js):
    """Inicia un proceso y lo almacena en el diccionario."""
    try:
        original_cwd = os.getcwd()
        os.chdir(route)
        
        process = subprocess.Popen(['node', file_js], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        processes[name] = process
        logger.info(f"Proceso '{name}' iniciado en {route}")

        def read_output():
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    logger.info(f"[{name}] {output.strip()}")
            
            stderr_output = process.stderr.read()
            if stderr_output:
                logger.error(f"[{name} ERROR] {stderr_output.strip()}")

        threading.Thread(target=read_output, daemon=True).start()
        
        os.chdir(original_cwd)
        
    except Exception as e:
        logger.error(f"Error en run_process para {name}: {e}")
        os.chdir(original_cwd)

def start_process(name):
    """Inicia un proceso específico."""
    try:
        if name in processes_list:
            process_info = processes_list[name]
            script_name = process_info['script']
            script_route = process_info['route']
            
            threading.Thread(target=run_process, args=(script_route, name, script_name), daemon=True).start()
            logger.info(f"Start process llamado para: {name}")
            return True
        else:
            logger.warning(f"Proceso {name} no encontrado en processes_list")
            return False
    except Exception as e:
        logger.error(f"Error en start_process para {name}: {e}")
        return False

def stop_process(name):
    """Detiene un proceso específico."""
    if name in processes:
        try:
            process = processes[name]
            process.terminate()
            process.wait(timeout=5)
            logger.info(f"Proceso '{name}' detenido correctamente.")
            del processes[name]
            return True
        except subprocess.TimeoutExpired:
            logger.warning(f"El proceso '{name}' no se detuvo a tiempo. Forzando la terminación.")
            processes[name].kill()
            processes[name].wait()
            del processes[name]
            return True
        except Exception as e:
            logger.error(f"Error al detener el proceso '{name}': {e}")
            return False
    else:
        logger.warning(f"No se encontró el proceso '{name}' para detener.")
        return False

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Iniciando aplicación en puerto {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
