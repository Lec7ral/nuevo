import os
import threading
import subprocess
import shutil
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from flask import Flask, request, render_template, url_for, send_file
import telebot

# Configuración inicial
BOT_API = os.environ['BOT_API']
SECRET = os.environ['SECRET']
URL = 'https://nuevo-uf5s.onrender.com'
ABSOLUTE_PATH = os.getcwd()

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Inicialización
app = Flask(__name__)
miBot = telebot.TeleBot(BOT_API)

# Gestor de procesos mejorado
class ProcessManager:
    def __init__(self):
        self.processes = {}
        self.processes_list = {}
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.lock = threading.Lock()
    
    def run_process(self, route, name, file_js):
        """Ejecuta proceso de manera más eficiente"""
        try:
            process = subprocess.Popen(
                ['node', file_js], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                universal_newlines=True,
                cwd=route,
                bufsize=1
            )
            
            with self.lock:
                self.processes[name] = process
            
            # Leer output de forma no bloqueante
            threading.Thread(
                target=self._capture_output, 
                args=(process, name),
                daemon=True
            ).start()
            
            logger.info(f"Proceso '{name}' iniciado en {route}")
            return True
        except Exception as e:
            logger.error(f"Error ejecutando proceso {name}: {e}")
            return False
    
    def _capture_output(self, process, name):
        """Captura output del proceso sin bloquear"""
        while process.poll() is None:
            try:
                output = process.stdout.readline()
                if output:
                    logger.info(f"[{name}] {output.strip()}")
            except Exception as e:
                logger.error(f"Error leyendo output de {name}: {e}")
                break

    def stop_process(self, name):
        """Detiene un proceso específico de manera segura"""
        with self.lock:
            if name in self.processes:
                try:
                    process = self.processes[name]
                    process.terminate()
                    process.wait(timeout=5)
                    del self.processes[name]
                    logger.info(f"Proceso '{name}' detenido correctamente")
                    return True
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    del self.processes[name]
                    logger.warning(f"Proceso '{name}' forzado a detenerse")
                    return True
                except Exception as e:
                    logger.error(f"Error deteniendo proceso '{name}': {e}")
                    return False
            return False

    def get_process_status(self):
        """Obtiene estado de todos los procesos"""
        status = {}
        with self.lock:
            for name, process in self.processes.items():
                status[name] = "🟢" if process.poll() is None else "🔴"
        return status

# Instancia global del gestor de procesos
process_manager = ProcessManager()

# Configurar webhook solo una vez al inicio
@app.before_first_request
def setup_webhook():
    miBot.remove_webhook()
    miBot.set_webhook(url=URL)
    logger.info("Webhook configurado")

# Rutas Flask optimizadas
@app.route('/', methods=['GET', 'POST'])
def webhook():
    if request.method == 'POST':
        update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
        miBot.process_new_updates([update])
        return 'ok', 200
    return 'Hello, World!'

@app.route('/files')
@app.route('/files/<path:path>')
def list_files(path='.'):
    """Unifica navegación de archivos"""
    try:
        if not os.path.exists(path):
            return "Path no encontrado", 404
        
        files = []
        parent_path = os.path.dirname(path) if path != '.' else None
        
        for item in sorted(os.listdir(path)):
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                files.append((f"📁 {item}/", url_for('list_files', path=item_path)))
            else:
                files.append((f"📄 {item}", url_for('serve_file', path=item_path)))
        
        return render_template('files.html', 
                             files=files, 
                             current_path=path,
                             parent_path=parent_path)
    except Exception as e:
        logger.error(f"Error listando archivos: {e}")
        return f"Error: {str(e)}", 500

@app.route('/files/download/<path:path>')
def serve_file(path):
    return send_file(path, as_attachment=True)

# Funciones de utilidad
def async_send_message(chat_id, text):
    """Envía mensajes de forma asíncrona"""
    def send():
        try:
            miBot.send_message(chat_id, text)
        except Exception as e:
            logger.error(f"Error enviando mensaje: {e}")
    
    threading.Thread(target=send, daemon=True).start()

def run_async_task(func, *args, **kwargs):
    """Ejecuta tareas en segundo plano"""
    threading.Thread(target=func, args=args, kwargs=kwargs, daemon=True).start()

# Comandos simples del bot
@miBot.message_handler(commands=["start"])
def cmd_start(message):
    miBot.send_message(message.chat.id, "✅ Bot funcionando correctamente")

@miBot.message_handler(commands=["enserio"])
def cmd_enserio(message):
    miBot.reply_to(message, "¡Sí, completamente en serio! 😄")

@miBot.message_handler(commands=["help"])
def cmd_help(message):
    help_text = """
🤖 **Comandos disponibles:**

**Básicos:**
/start - Iniciar el bot
/enserio - Respuesta divertida
/help - Muestra esta ayuda

**Gestión de archivos:**
/ls [ruta] - Listar archivos y carpetas
/mkdir <nombre> - Crear carpeta
/cd <ruta> - Cambiar directorio
/rm <nombre> - Eliminar archivo/carpeta
/mv <origen> <destino> - Mover
/zip <carpeta> - Comprimir
/unzip <archivo> - Descomprimir
/up <archivo> - Subir archivo

**Procesos Node.js:**
/inst - Instalar entorno Node.js
/modules <módulos> - Instalar módulos
/run <nombre> - Ejecutar script
/act - Procesos activos
/stop <nombre> - Detener proceso
/list - Listar procesos con botones

**Web:**
/files - Explorador de archivos web
    """
    miBot.send_message(message.chat.id, help_text, parse_mode='Markdown')

# Gestión de procesos con botones
def create_process_buttons():
    """Crea botones para los procesos"""
    keyboard = telebot.types.InlineKeyboardMarkup()
    status = process_manager.get_process_status()
    
    for name in process_manager.processes_list.keys():
        btn_status = status.get(name, "🔴")
        keyboard.add(telebot.types.InlineKeyboardButton(
            f"{btn_status} {name}", 
            callback_data=f"process_{name}"
        ))
    
    keyboard.add(telebot.types.InlineKeyboardButton(
        "➕ Agregar Proceso", 
        callback_data="add_process"
    ))
    return keyboard

@miBot.message_handler(commands=['list'])
def list_processes(message):
    """Muestra procesos con botones interactivos"""
    keyboard = create_process_buttons()
    miBot.send_message(message.chat.id, "🔧 **Gestión de Procesos:**", 
                      reply_markup=keyboard, parse_mode='Markdown')

@miBot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    """Maneja interacciones con botones"""
    if call.data == "add_process":
        miBot.send_message(call.message.chat.id, 
                          "📝 Envía el nombre de la carpeta del proceso:")
        miBot.register_next_step_handler(call.message, add_process_step)
    
    elif call.data.startswith("process_"):
        process_name = call.data[8:]  # Remueve "process_" prefix
        if process_name in process_manager.processes:
            if process_manager.stop_process(process_name):
                async_send_message(call.message.chat.id, f"⏹️ Proceso '{process_name}' detenido")
            else:
                async_send_message(call.message.chat.id, f"❌ Error deteniendo '{process_name}'")
        else:
            # Intentar iniciar el proceso
            if process_name in process_manager.processes_list:
                start_process(process_name)
                async_send_message(call.message.chat.id, f"▶️ Proceso '{process_name}' iniciado")
    
    # Actualizar botones
    try:
        keyboard = create_process_buttons()
        miBot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, 
                                      reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Error actualizando botones: {e}")

def add_process_step(message):
    """Agrega nuevo proceso paso a paso"""
    try:
        process_name = message.text.strip()
        script_path = os.path.join(ABSOLUTE_PATH, process_name, "meomundep.js")
        absolute_path = os.path.join(ABSOLUTE_PATH, process_name)

        if not os.path.isfile(script_path):
            miBot.send_message(message.chat.id, 
                             f"❌ El script 'meomundep.js' no existe en {process_name}/")
            return

        process_manager.processes_list[process_name] = {
            'script': "meomundep.js",
            'route': absolute_path
        }
        
        start_process(process_name)
        miBot.send_message(message.chat.id, 
                         f"✅ Proceso '{process_name}' agregado y en ejecución")
    
    except Exception as e:
        miBot.send_message(message.chat.id, f"❌ Error agregando proceso: {e}")

# Comandos de instalación y módulos
@miBot.message_handler(commands=["inst"])
def cmd_install(message):
    """Instalación optimizada del entorno"""
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
                async_send_message(message.chat.id, step_name)
                result = subprocess.run(command, capture_output=True, text=True, cwd=ABSOLUTE_PATH)
                if result.returncode != 0:
                    async_send_message(message.chat.id, 
                                     f"❌ Error en {step_name}:\n{result.stderr}")
                    return
            
            async_send_message(message.chat.id, "✅ Instalación completada")
            
        except Exception as e:
            async_send_message(message.chat.id, f"❌ Error en instalación: {e}")
    
    run_async_task(install_task)
    miBot.reply_to(message, "🚀 Iniciando instalación... Esto puede tomar unos minutos.")

@miBot.message_handler(commands=["modules"])
def cmd_modules(message):
    """Instala módulos adicionales"""
    modules_to_install = message.text.split()[1:]
    if not modules_to_install:
        miBot.reply_to(message, "📝 Uso: /modules <módulo1> <módulo2> ...")
        return
    
    def install_modules_task():
        try:
            async_send_message(message.chat.id, f"📦 Instalando: {', '.join(modules_to_install)}")
            result = subprocess.run(['npm', 'i'] + modules_to_install, 
                                 capture_output=True, text=True, cwd=ABSOLUTE_PATH)
            
            if result.returncode == 0:
                async_send_message(message.chat.id, "✅ Módulos instalados correctamente")
                if result.stdout:
                    async_send_message(message.chat.id, f"📄 Output:\n{result.stdout[:1000]}...")
            else:
                async_send_message(message.chat.id, f"❌ Error:\n{result.stderr}")
                
        except Exception as e:
            async_send_message(message.chat.id, f"❌ Error instalando módulos: {e}")
    
    run_async_task(install_modules_task)

# Comandos de sistema de archivos
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
        
        # Formatear respuesta
        folders = [f"📁 {item}/" for item in items if os.path.isdir(os.path.join(path, item))]
        files = [f"📄 {item}" for item in items if os.path.isfile(os.path.join(path, item))]
        
        response = f"📂 Contenido de '{path}':\n\n"
        if folders:
            response += "**Carpetas:**\n" + "\n".join(folders) + "\n\n"
        if files:
            response += "**Archivos:**\n" + "\n".join(files)
        
        # Dividir si es muy largo
        if len(response) > 4000:
            response = response[:4000] + "\n... (lista truncada)"
            
        miBot.reply_to(message, response, parse_mode='Markdown')
        
    except Exception as e:
        miBot.reply_to(message, f"❌ Error listando archivos: {str(e)}")

@miBot.message_handler(commands=["mkdir"])
def cmd_mkdir(message):
    """Crea directorio"""
    try:
        folder_name = message.text[6:].strip()
        if not folder_name:
            miBot.reply_to(message, "📝 Uso: /mkdir <nombre_carpeta>")
            return
        
        os.makedirs(folder_name, exist_ok=True)
        miBot.reply_to(message, f"✅ Carpeta '{folder_name}' creada")
        
    except Exception as e:
        miBot.reply_to(message, f"❌ Error creando carpeta: {str(e)}")

@miBot.message_handler(commands=["cd"])
def cmd_cd(message):
    """Cambia directorio"""
    try:
        dir_name = message.text[3:].strip()
        if not dir_name:
            miBot.reply_to(message, "📝 Uso: /cd <ruta>")
            return
        
        if not os.path.exists(dir_name):
            miBot.reply_to(message, f"❌ Directorio no existe: {dir_name}")
            return
            
        os.chdir(dir_name)
        current_dir = os.getcwd()
        miBot.reply_to(message, f"📂 Directorio cambiado a:\n{current_dir}")
        
    except Exception as e:
        miBot.reply_to(message, f"❌ Error cambiando directorio: {str(e)}")

@miBot.message_handler(commands=["rm"])
def cmd_rm(message):
    """Elimina archivo o carpeta"""
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
            miBot.reply_to(message, f"✅ Carpeta '{item_name}' eliminada")
        else:
            os.remove(item_name)
            miBot.reply_to(message, f"✅ Archivo '{item_name}' eliminado")
            
    except Exception as e:
        miBot.reply_to(message, f"❌ Error eliminando: {str(e)}")

@miBot.message_handler(commands=["mv"])
def cmd_move(message):
    """Mueve archivo o carpeta"""
    try:
        args = message.text.split()[1:]
        if len(args) != 2:
            miBot.reply_to(message, "📝 Uso: /mv <origen> <destino>")
            return
        
        origen, destino = args
        shutil.move(origen, destino)
        miBot.reply_to(message, f"✅ Movido '{origen}' → '{destino}'")
        
    except Exception as e:
        miBot.reply_to(message, f"❌ Error moviendo: {str(e)}")

@miBot.message_handler(commands=["zip"])
def cmd_zip(message):
    """Comprime carpeta"""
    try:
        folder_name = message.text[4:].strip()
        if not folder_name:
            miBot.reply_to(message, "📝 Uso: /zip <carpeta>")
            return
        
        if not os.path.exists(folder_name):
            miBot.reply_to(message, f"❌ Carpeta no existe: {folder_name}")
            return
        
        shutil.make_archive(folder_name, 'zip', folder_name)
        miBot.reply_to(message, f"✅ Comprimido: '{folder_name}.zip'")
        
    except Exception as e:
        miBot.reply_to(message, f"❌ Error comprimiendo: {str(e)}")

@miBot.message_handler(commands=["unzip"])
def cmd_unzip(message):
    """Descomprime archivo"""
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
        miBot.reply_to(message, f"✅ Descomprimido: '{zip_file}' → '{extract_dir}'")
        
    except Exception as e:
        miBot.reply_to(message, f"❌ Error descomprimiendo: {str(e)}")

@miBot.message_handler(commands=["up"])
def cmd_sendfile(message):
    """Envía archivo"""
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
        miBot.reply_to(message, f"❌ Error enviando archivo: {str(e)}")

# Manejo de documentos subidos
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
            
            # Procesar ZIP automáticamente
            if file_name.endswith('.zip'):
                extract_dir = file_name.replace('.zip', '')
                shutil.unpack_archive(file_name, extract_dir)
                os.remove(file_name)
                async_send_message(message.chat.id, 
                                 f"✅ ZIP descomprimido: '{extract_dir}'")
            else:
                async_send_message(message.chat.id, f"✅ Archivo guardado: '{file_name}'")
                
        except Exception as e:
            async_send_message(message.chat.id, f"❌ Error procesando archivo: {e}")
    
    run_async_task(process_document)
    miBot.reply_to(message, "📤 Procesando archivo...")

# Comandos de procesos
@miBot.message_handler(commands=["run"])
def cmd_run_js(message):
    """Ejecuta proceso"""
    try:
        args = message.text.split()
        if len(args) < 2:
            miBot.reply_to(message, "📝 Uso: /run <nombre_proceso>")
            return
        
        process_name = args[1]
        start_process(process_name)
        miBot.reply_to(message, f"🚀 Iniciando proceso '{process_name}'...")
        
    except Exception as e:
        miBot.reply_to(message, f"❌ Error iniciando proceso: {e}")

@miBot.message_handler(commands=["act"])
def cmd_processes_activ(message):
    """Lista procesos activos"""
    if not process_manager.processes:
        miBot.reply_to(message, "📭 No hay procesos en ejecución")
        return
    
    message_text = "🟢 **Procesos Activos:**\n"
    for name, process in process_manager.processes.items():
        status = "🟢 Ejecutándose" if process.poll() is None else "🔴 Detenido"
        message_text += f"• {name}: {status} (PID: {process.pid})\n"
    
    miBot.reply_to(message, message_text, parse_mode='Markdown')

@miBot.message_handler(commands=["stop"])
def cmd_stop_js(message):
    """Detiene proceso"""
    try:
        args = message.text.split()
        if len(args) < 2:
            miBot.reply_to(message, "📝 Uso: /stop <nombre_proceso>")
            return
        
        process_name = args[1]
        if process_manager.stop_process(process_name):
            miBot.reply_to(message, f"⏹️ Proceso '{process_name}' detenido")
        else:
            miBot.reply_to(message, f"❌ Proceso '{process_name}' no encontrado")
            
    except Exception as e:
        miBot.reply_to(message, f"❌ Error deteniendo proceso: {e}")

# Funciones de procesos
def start_process(name):
    """Inicia un proceso"""
    try:
        if name in process_manager.processes_list:
            process_info = process_manager.processes_list[name]
            script_name = process_info['script']
            script_route = process_info['route']
            
            if process_manager.run_process(script_route, name, script_name):
                logger.info(f"Proceso {name} iniciado correctamente")
                return True
        else:
            logger.warning(f"Proceso {name} no encontrado en processes_list")
        return False
    except Exception as e:
        logger.error(f"Error en start_process para {name}: {e}")
        return False

# Configuración e inicio
if __name__ == '__main__':
    # Configuración para producción
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Iniciando aplicación en puerto {port} (debug: {debug})")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug,
        threaded=True
    )
