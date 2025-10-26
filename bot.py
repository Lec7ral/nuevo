import os
import threading
import subprocess
import shutil
import time
import logging
import zipfile
import json
import re
from pathlib import Path
from collections import deque
from datetime import datetime, timedelta
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

# Configuración por defecto (persistente)
DEFAULT_CONFIG = {
    'max_concurrent_processes': 3,
    'restart_delay': 30,
    'stop_keywords': ['Waiting', 'Bot broken somewhere'],
    'login_failed_pattern': True,
    'process_check_interval': 10
}

# Archivos de persistencia
CONFIG_FILE = 'bot_config.json'
PROCESSES_FILE = 'processes_list.json'
STATS_FILE = 'process_stats.json'

# Cargar configuración
def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except:
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def load_processes_list():
    try:
        with open(PROCESSES_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_processes_list():
    with open(PROCESSES_FILE, 'w') as f:
        json.dump(processes_list, f, indent=2)

def load_process_stats():
    try:
        with open(STATS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_process_stats():
    with open(STATS_FILE, 'w') as f:
        json.dump(process_stats, f, indent=2)

# Cargar datos persistentes al inicio
config = load_config()
MAX_CONCURRENT_PROCESSES = config['max_concurrent_processes']
RESTART_DELAY = config['restart_delay']
STOP_KEYWORDS = config['stop_keywords']
LOGIN_FAILED_PATTERN = config['login_failed_pattern']
PROCESS_CHECK_INTERVAL = config['process_check_interval']

# Inicialización
app = Flask(__name__)
miBot = telebot.TeleBot(BOT_API, parse_mode=None)

# Configurar webhook al inicio
with app.app_context():
    miBot.remove_webhook()
    miBot.set_webhook(url=URL)
    logger.info("Webhook configurado")

# Estructuras para gestión de procesos
processes = {}
processes_list = load_processes_list()
process_stats = load_process_stats()
process_queue = deque()
users_adding_process = {}

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

# Comando de configuración
@miBot.message_handler(commands=["config"])
def cmd_config(message):
    """Configura los parámetros del bot en tiempo real"""
    try:
        args = message.text.split()
        if len(args) < 3:
            show_current_config(message)
            return

        setting = args[1].lower()
        value = args[2]

        if setting == "max_processes":
            new_max = int(value)
            if new_max < 1:
                miBot.reply_to(message, "❌ El número de procesos debe ser al menos 1")
                return
            config['max_concurrent_processes'] = new_max
            global MAX_CONCURRENT_PROCESSES
            MAX_CONCURRENT_PROCESSES = new_max
            save_config(config)
            miBot.reply_to(message, f"✅ Límite de procesos cambiado a {new_max}")

        elif setting == "restart_delay":
            new_delay = int(value)
            if new_delay < 5:
                miBot.reply_to(message, "❌ El delay de reinicio debe ser al menos 5 segundos")
                return
            config['restart_delay'] = new_delay
            global RESTART_DELAY
            RESTART_DELAY = new_delay
            save_config(config)
            miBot.reply_to(message, f"✅ Delay de reinicio cambiado a {new_delay} segundos")

        elif setting == "stop_keywords":
            # Agregar nueva palabra clave para detener procesos
            if value not in STOP_KEYWORDS:
                STOP_KEYWORDS.append(value)
                config['stop_keywords'] = STOP_KEYWORDS
                save_config(config)
                miBot.reply_to(message, f"✅ Palabra clave '{value}' agregada para detección")
            else:
                miBot.reply_to(message, f"❌ La palabra clave '{value}' ya existe")

        else:
            miBot.reply_to(message, "❌ Configuración no válida. Usa: max_processes, restart_delay o stop_keywords")

    except ValueError:
        miBot.reply_to(message, "❌ El valor debe ser un número")
    except Exception as e:
        logger.error(f"Error en configuración: {e}")
        miBot.reply_to(message, f"❌ Error en configuración: {e}")

def show_current_config(message):
    """Muestra la configuración actual"""
    config_text = f"""
⚙️ **Configuración Actual:**

• Límite de procesos: {MAX_CONCURRENT_PROCESSES}
• Delay de reinicio: {RESTART_DELAY}s
• Palabras de detección: {', '.join(STOP_KEYWORDS)}
• Detección login failed: {'✅ Activado' if LOGIN_FAILED_PATTERN else '❌ Desactivado'}

**Uso:** `/config <max_processes|restart_delay|stop_keywords> <valor>`
"""
    miBot.reply_to(message, config_text, parse_mode='Markdown')

# Gestión de procesos con botones
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
    
    keyboard.add(telebot.types.InlineKeyboardButton(
        "🔄 Verificar Cola", 
        callback_data=f"check_queue_{current_time}"
    ))
    
    return keyboard

@miBot.message_handler(commands=['list'])
def list_processes(message):
    """Muestra los procesos en ejecución con botones."""
    keyboard = create_process_buttons()
    status_info = f"🔧 **Gestión de Procesos**\n\n🟢 Ejecutándose: {count_running_processes()}/{MAX_CONCURRENT_PROCESSES}\n📊 En cola: {len(process_queue)}"
    miBot.send_message(message.chat.id, status_info, reply_markup=keyboard)

@miBot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    """Maneja las interacciones con los botones"""
    try:
        logger.info(f"Callback recibido: {call.data}")
        
        parts = call.data.split('_')
        action_type = parts[0]
        
        if action_type == "add":
            miBot.answer_callback_query(call.id, "Por favor envía el nombre de la carpeta del proceso")
            users_adding_process[call.from_user.id] = True
            
            msg = miBot.send_message(
                call.message.chat.id, 
                "📝 **Agregar Nuevo Proceso**\n\nPor favor, envía el nombre de la carpeta donde está el script meomundep.js:",
                parse_mode='Markdown'
            )
            
        elif action_type == "process":
            if len(parts) >= 2:
                process_name = parts[1]
                
                if process_name in processes and processes[process_name].poll() is None:
                    if stop_process(process_name):
                        miBot.answer_callback_query(call.id, f"⏹️ {process_name} detenido")
                    else:
                        miBot.answer_callback_query(call.id, f"❌ Error deteniendo {process_name}")
                else:
                    if start_process(process_name):
                        miBot.answer_callback_query(call.id, f"▶️ {process_name} iniciado")
                    else:
                        miBot.answer_callback_query(call.id, f"⏳ {process_name} en cola (posición: {len(process_queue)})")
            
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

        elif action_type == "check":
            process_queue_from_waiting()
            miBot.answer_callback_query(call.id, "✅ Cola verificada")
            
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

# Handler para mensajes de texto que podrían ser nombres de procesos
@miBot.message_handler(func=lambda message: message.from_user.id in users_adding_process, content_types=['text'])
def handle_process_name_input(message):
    """Maneja la entrada del nombre del proceso para usuarios que están en modo agregar"""
    try:
        user_id = message.from_user.id
        
        if user_id not in users_adding_process:
            return
        
        del users_adding_process[user_id]
        
        process_name = message.text.strip()
        
        if not process_name:
            miBot.reply_to(message, "❌ El nombre del proceso no puede estar vacío.")
            return
        
        folder_path = os.path.join(ABSOLUTE_PATH, process_name)
        if not os.path.exists(folder_path):
            miBot.reply_to(message, f"❌ La carpeta '{process_name}' no existe.")
            return
        
        script_path = os.path.join(folder_path, "meomundep.js")
        if not os.path.isfile(script_path):
            miBot.reply_to(message, f"❌ El script 'meomundep.js' no existe en la carpeta '{process_name}'.")
            return
        
        processes_list[process_name] = {
            'script': "meomundep.js",
            'route': folder_path
        }
        
        save_processes_list()
        
        if start_process(process_name):
            miBot.reply_to(message, f"✅ Proceso '{process_name}' agregado y en ejecución.")
        else:
            miBot.reply_to(message, f"⏳ Proceso '{process_name}' agregado a la cola (posición: {len(process_queue)}).")
        
        try:
            keyboard = create_process_buttons()
            miBot.send_message(message.chat.id, "🔧 **Gestión de Procesos Actualizada:**", reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Error enviando teclado actualizado: {e}")
            
    except Exception as e:
        logger.error(f"Error en handle_process_name_input: {e}")
        miBot.reply_to(message, f"❌ Error al agregar el proceso: {e}")

# FUNCIONALIDAD 1: Carga automática de scripts desde ZIP (SOLO PRIMER NIVEL)
def find_and_load_scripts_from_directory(directory):
    """Busca y carga automáticamente scripts meomundep.js solo en el primer nivel del directorio."""
    try:
        scripts_found = []
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            if os.path.isdir(item_path):
                script_path = os.path.join(item_path, "meomundep.js")
                if os.path.isfile(script_path):
                    folder_name = item
                    
                    if folder_name not in processes_list:
                        processes_list[folder_name] = {
                            'script': "meomundep.js",
                            'route': item_path
                        }
                        scripts_found.append(folder_name)
                        logger.info(f"Script encontrado y cargado: {folder_name}")
        
        if scripts_found:
            save_processes_list()
                
        return scripts_found
    except Exception as e:
        logger.error(f"Error buscando scripts en {directory}: {e}")
        return []

@miBot.message_handler(content_types=['document'])
def handle_document(message):
    """Procesa archivos subidos - CON CARGA AUTOMÁTICA DE SCRIPTS (solo primer nivel)"""
    def process_document():
        try:
            file_info = miBot.get_file(message.document.file_id)
            downloaded_file = miBot.download_file(file_info.file_path)
            file_name = message.document.file_name
            
            with open(file_name, 'wb') as f:
                f.write(downloaded_file)
            
            if file_name.endswith('.zip'):
                extract_dir = file_name.replace('.zip', '')
                
                os.makedirs(extract_dir, exist_ok=True)
                
                with zipfile.ZipFile(file_name, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                
                loaded_scripts = find_and_load_scripts_from_directory(extract_dir)
                
                os.remove(file_name)
                
                if loaded_scripts:
                    script_list = "\n".join([f"• {script}" for script in loaded_scripts])
                    response_msg = f"✅ **ZIP procesado correctamente**\n\n📂 Carpeta: {extract_dir}\n🔧 Scripts cargados automáticamente:\n{script_list}\n\nUsa /list para gestionar los procesos."
                    
                    auto_started = 0
                    for script_name in loaded_scripts:
                        if start_process(script_name):
                            auto_started += 1
                    
                    if auto_started > 0:
                        response_msg += f"\n\n🚀 {auto_started} procesos iniciados automáticamente."
                    else:
                        response_msg += f"\n\n⏳ {len(loaded_scripts) - auto_started} procesos en cola (límite alcanzado)."
                    
                    miBot.send_message(message.chat.id, response_msg, parse_mode='Markdown')
                else:
                    miBot.send_message(
                        message.chat.id, 
                        f"✅ ZIP descomprimido: '{extract_dir}'\n❌ No se encontraron scripts meomundep.js en el primer nivel para cargar automáticamente."
                    )
            else:
                miBot.send_message(message.chat.id, f"✅ Archivo guardado: '{file_name}'")
                
        except Exception as e:
            logger.error(f"Error procesando archivo: {e}")
            miBot.send_message(message.chat.id, f"❌ Error procesando archivo: {e}")
    
    threading.Thread(target=process_document, daemon=True).start()
    miBot.reply_to(message, "📤 Procesando archivo y buscando scripts automáticamente...")

# SISTEMA DE DETECCIÓN DE PALABRAS CLAVE (BASADO EN TU CÓDIGO ORIGINAL)
def detect_stop_conditions(output, process_name):
    """
    Detecta condiciones específicas en el output que requieren detener el proceso.
    Basado en tu código original.
    """
    try:
        # 1. Detectar "Waiting"
        if "Waiting" in output:
            logger.info(f"⏸️ '{process_name}' está en espera. Deteniendo el proceso.")
            return True, "en espera"
        
        # 2. Detectar "Bot broken somewhere"
        if "Bot broken somewhere" in output:
            logger.info(f"🛑 '{process_name}' se rompió. Deteniendo el proceso.")
            return True, "bot roto"
        
        # 3. Detectar patron de login failed (con regex como en tu código original)
        if LOGIN_FAILED_PATTERN:
            try:
                if re.search(r'login', output, re.IGNORECASE) and re.search(r'failed', output, re.IGNORECASE):
                    logger.info(f"🔐 '{process_name}' ha fallado en el login. Deteniendo el proceso.")
                    
                    # Enviar mensaje al chat específico (como en tu código original)
                    try:
                        miBot.send_message(971580959, f"Error de inicio de sesión en '{process_name}'.")
                    except Exception as e:
                        logger.error(f"Error enviando mensaje de login failed: {e}")
                    
                    return True, "error de login"
            except Exception as e:
                logger.error(f"Error en detección de login failed: {e}")
        
        return False, None
        
    except Exception as e:
        logger.error(f"Error en detección de condiciones: {e}")
        return False, None

def count_running_processes():
    """Cuenta cuántos procesos están actualmente en ejecución."""
    count = 0
    for name, process in processes.items():
        if process.poll() is None:
            count += 1
    return count

def schedule_restart_to_queue(process_name, delay=RESTART_DELAY, reason="condición detectada"):
    """Programa el agregado del proceso a la cola después de un delay."""
    def add_to_queue():
        logger.info(f"⏰ Programando agregado a cola de {process_name} en {delay} segundos...")
        time.sleep(delay)
        
        if process_name in processes_list:
            if process_name not in process_queue:
                process_queue.append(process_name)
                logger.info(f"🔄 {process_name} agregado al FINAL de la cola después de {reason}")
            else:
                logger.info(f"ℹ️ {process_name} ya está en la cola")
        else:
            logger.warning(f"❌ No se puede agregar {process_name} a la cola: no está en la lista")
    
    threading.Thread(target=add_to_queue, daemon=True).start()

def process_queue_from_waiting():
    """Procesa la cola de espera si hay espacio disponible."""
    running_count = count_running_processes()
    
    while process_queue and running_count < MAX_CONCURRENT_PROCESSES:
        process_name = process_queue.popleft()
        logger.info(f"🔄 Procesando {process_name} desde la cola...")
        
        if start_process_direct(process_name):
            running_count += 1
            logger.info(f"✅ {process_name} iniciado desde cola")
        else:
            logger.error(f"❌ Error iniciando {process_name} desde cola")
            process_queue.appendleft(process_name)
            break

def start_process_direct(process_name):
    """Inicia un proceso directamente sin verificar cola (uso interno)."""
    try:
        if process_name in processes_list:
            process_info = processes_list[process_name]
            script_name = process_info['script']
            script_route = process_info['route']
            
            if process_name not in process_stats:
                process_stats[process_name] = {
                    'start_time': time.time(),
                    'stop_count': 0,
                    'total_uptime': 0,
                    'last_stop_reason': None,
                    'last_stop_time': None
                }
            else:
                process_stats[process_name]['start_time'] = time.time()
            
            threading.Thread(
                target=run_process_with_monitoring, 
                args=(script_route, process_name, script_name), 
                daemon=True
            ).start()
            logger.info(f"Start process direct llamado para: {process_name}")
            return True
        else:
            logger.warning(f"Proceso {process_name} no encontrado en processes_list")
            return False
    except Exception as e:
        logger.error(f"Error en start_process_direct para {process_name}: {e}")
        return False

def start_process(process_name):
    """Inicia un proceso con verificación de límites."""
    running_count = count_running_processes()
    
    if running_count >= MAX_CONCURRENT_PROCESSES:
        if process_name not in process_queue:
            process_queue.append(process_name)
            logger.info(f"⏳ {process_name} agregado a la cola. Posición: {len(process_queue)}")
        return False
    else:
        return start_process_direct(process_name)

def run_process_with_monitoring(route, name, file_js):
    """
    Inicia un proceso con monitoreo de output para detectar condiciones de parada.
    Basado en tu código original pero integrado con el sistema de colas.
    """
    try:
        original_cwd = os.getcwd()
        os.chdir(route)
        
        process = subprocess.Popen(
            ['node', file_js], 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            universal_newlines=True,
            bufsize=1
        )
        processes[name] = process
        logger.info(f"🔄 Proceso '{name}' iniciado en {route}")

        def monitor_output():
            """Monitorea la salida del proceso para detectar condiciones de parada."""
            try:
                while True:
                    output = process.stdout.readline()
                    
                    # Salir si el proceso ha terminado (como en tu código original)
                    if output == '' and process.poll() is not None:
                        break
                    
                    if output:
                        output_clean = output.strip()
                        logger.info(f"[{name}] {output_clean}")
                        
                        # DETECCIÓN DE CONDICIONES DE PARADA (tu lógica original)
                        should_stop, stop_reason = detect_stop_conditions(output_clean, name)
                        
                        if should_stop:
                            logger.warning(f"🛑 Condición de parada detectada en {name}: {stop_reason}. Deteniendo proceso...")
                            
                            # Actualizar estadísticas
                            if name in process_stats:
                                process_stats[name]['stop_count'] += 1
                                process_stats[name]['last_stop_reason'] = stop_reason
                                process_stats[name]['last_stop_time'] = time.time()
                                process_stats[name]['total_uptime'] += time.time() - process_stats[name]['start_time']
                            
                            # Detener proceso actual
                            try:
                                process.terminate()
                                process.wait(timeout=10)
                            except:
                                process.kill()
                            
                            # Eliminar del diccionario de procesos
                            if name in processes:
                                del processes[name]
                            
                            # Programar agregado a cola (NO REINICIO DIRECTO)
                            schedule_restart_to_queue(name, reason=stop_reason)
                            
                            # Procesar siguiente en cola inmediatamente
                            process_queue_from_waiting()
                            break
                
                # Si el proceso termina por sí solo (sin condición de parada)
                if process.poll() is not None:
                    return_code = process.returncode
                    
                    # Actualizar estadísticas de tiempo
                    if name in process_stats:
                        end_time = time.time()
                        uptime = end_time - process_stats[name]['start_time']
                        process_stats[name]['total_uptime'] += uptime
                    
                    if return_code != 0:
                        logger.warning(f"⚠️ Proceso {name} terminó con código {return_code}. Agregando a cola...")
                        schedule_restart_to_queue(name, reason=f"exit code: {return_code}")
                    else:
                        logger.info(f"✅ Proceso {name} terminó exitosamente")
                        # No se reagrega a la cola si terminó exitosamente
                
                # Liberar espacio para siguiente proceso en cola
                process_queue_from_waiting()
                
                # Guardar estadísticas
                save_process_stats()
                
            except Exception as e:
                logger.error(f"Error en monitor_output para {name}: {e}")
                schedule_restart_to_queue(name, reason=f"exception: {e}")

        # Iniciar monitoreo en hilo separado
        threading.Thread(target=monitor_output, daemon=True).start()
        
        os.chdir(original_cwd)
        
    except Exception as e:
        logger.error(f"Error en run_process_with_monitoring para {name}: {e}")
        try:
            os.chdir(original_cwd)
        except:
            pass
        schedule_restart_to_queue(name, reason=f"startup error: {e}")

# Los comandos restantes se mantienen igual (inst, modules, stats, help, ls, mkdir, cd, rm, mv, zip, unzip, up, run, act, stop)
@miBot.message_handler(commands=["inst"])
def cmd_install(message):
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

@miBot.message_handler(commands=["stats"])
def cmd_stats(message):
    """Muestra estadísticas de rendimiento de los procesos"""
    try:
        if not process_stats:
            miBot.reply_to(message, "📊 No hay estadísticas disponibles")
            return
        
        stats_text = "📊 **Estadísticas de Procesos**\n\n"
        
        for name, stats in process_stats.items():
            total_uptime = stats.get('total_uptime', 0)
            stop_count = stats.get('stop_count', 0)
            last_stop_reason = stats.get('last_stop_reason', 'Ninguno')
            last_stop_time = stats.get('last_stop_time')
            
            # Calcular tiempo actual si está ejecutándose
            current_uptime = 0
            if name in processes and processes[name].poll() is None:
                current_uptime = time.time() - stats.get('start_time', time.time())
                total_with_current = total_uptime + current_uptime
                uptime_str = f"{timedelta(seconds=int(total_with_current))} (+{timedelta(seconds=int(current_uptime))})"
            else:
                uptime_str = str(timedelta(seconds=int(total_uptime)))
            
            # Formatear última parada
            last_stop_str = "Nunca"
            if last_stop_time:
                last_stop_str = f"{timedelta(seconds=int(time.time() - last_stop_time))} ago"
            
            stats_text += f"**{name}**\n"
            stats_text += f"• Tiempo total: {uptime_str}\n"
            stats_text += f"• Paradas por detección: {stop_count}\n"
            stats_text += f"• Última parada: {last_stop_reason}\n"
            stats_text += f"• Hace: {last_stop_str}\n\n"
        
        miBot.reply_to(message, stats_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error mostrando estadísticas: {e}")
        miBot.reply_to(message, f"❌ Error mostrando estadísticas: {e}")

@miBot.message_handler(commands=["help"])
def cmd_help(message):
    help_text = f"""
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
/config - Configurar parámetros del bot
/stats - Estadísticas de procesos

**⚙️ Configuración Actual:**
• Límite de procesos: {MAX_CONCURRENT_PROCESSES}
• Delay de reinicio: {RESTART_DELAY}s
• Palabras de detección: {', '.join(STOP_KEYWORDS)}
"""
    miBot.reply_to(message, help_text, parse_mode=None)

# Los comandos de sistema de archivos se mantienen igual (ls, mkdir, cd, rm, mv, zip, unzip, up, run, act, stop)
@miBot.message_handler(commands=["ls"])
def cmd_ls(message):
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
        
        loaded_scripts = find_and_load_scripts_from_directory(extract_dir)
        
        response = f"✅ Descomprimido: '{zip_file}' → '{extract_dir}'"
        if loaded_scripts:
            response += f"\n🔧 Scripts cargados: {len(loaded_scripts)}"
        
        miBot.reply_to(message, response)
    except Exception as e:
        miBot.reply_to(message, f"❌ Error: {str(e)}")

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
            miBot.reply_to(message, f"⏳ Proceso '{process_name}' en cola (posición: {len(process_queue)})")
    except Exception as e:
        miBot.reply_to(message, f"❌ Error: {str(e)}")

@miBot.message_handler(commands=["act"])
def cmd_processes_activ(message):
    if not processes and not process_queue:
        miBot.reply_to(message, "📭 No hay procesos en ejecución ni en cola")
        return
    
    message_text = f"🟢 Procesos Activos: {count_running_processes()}/{MAX_CONCURRENT_PROCESSES}\n"
    message_text += f"📊 En cola: {len(process_queue)}\n\n"
    
    running_found = False
    for name, process in list(processes.items()):
        if process.poll() is None:
            if not running_found:
                message_text += "**Ejecutándose:**\n"
                running_found = True
            message_text += f"• {name}: 🟢 (PID: {process.pid})\n"
        else:
            message_text += f"• {name}: 🔴 Terminado\n"
            del processes[name]
    
    if process_queue:
        message_text += f"\n**En cola:**\n"
        for i, name in enumerate(list(process_queue)[:10]):
            message_text += f"• {name} (posición: {i+1})\n"
        if len(process_queue) > 10:
            message_text += f"... y {len(process_queue) - 10} más\n"
    
    miBot.reply_to(message, message_text, parse_mode='Markdown')

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

def stop_process(name):
    """Detiene un proceso específico."""
    if name in processes:
        try:
            process = processes[name]
            process.terminate()
            process.wait(timeout=5)
            logger.info(f"Proceso '{name}' detenido correctamente.")
            
            if name in process_stats:
                end_time = time.time()
                uptime = end_time - process_stats[name]['start_time']
                process_stats[name]['total_uptime'] += uptime
                save_process_stats()
            
            del processes[name]
            
            process_queue_from_waiting()
            return True
        except subprocess.TimeoutExpired:
            logger.warning(f"El proceso '{name}' no se detuvo a tiempo. Forzando la terminación.")
            processes[name].kill()
            processes[name].wait()
            
            if name in process_stats:
                end_time = time.time()
                uptime = end_time - process_stats[name]['start_time']
                process_stats[name]['total_uptime'] += uptime
                save_process_stats()
            
            del processes[name]
            
            process_queue_from_waiting()
            return True
        except Exception as e:
            logger.error(f"Error al detener el proceso '{name}': {e}")
            return False
    else:
        logger.warning(f"No se encontró el proceso '{name}' para detener.")
        return False

# Iniciar verificación periódica de la cola
def start_queue_monitor():
    def monitor():
        while True:
            try:
                process_queue_from_waiting()
                time.sleep(PROCESS_CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"Error en monitor de cola: {e}")
                time.sleep(PROCESS_CHECK_INTERVAL)
    
    threading.Thread(target=monitor, daemon=True).start()

# Iniciar el monitor al cargar el bot
start_queue_monitor()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Iniciando aplicación en puerto {port}")
    logger.info(f"Configuración: {MAX_CONCURRENT_PROCESSES} procesos máx, {RESTART_DELAY}s delay")
    logger.info(f"Palabras de detección: {STOP_KEYWORDS}")
    app.run(host='0.0.0.0', port=port, debug=debug)
