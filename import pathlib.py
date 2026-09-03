from pathlib import Path
from datetime import datetime
import platform, os, time, threading, signal, subprocess, tempfile
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from croniter import croniter
dados_lock = threading.Lock()
dados = {}
parar_execucao = threading.Event()
def get_filesdir():
    if platform.system() == "Linux":
        return Path("/etc/scheduler") 
    elif platform.system() == "Windows":
        return Path(f"{os.environ.get('ProgramData')}\\scheduler\\files")
def get_configuration():
    if platform.system() == "Linux":
        return Path("/etc/scheduler.conf") 
    elif platform.system() == "Windows":
        return Path(f"{os.environ.get('ProgramData')}\\scheduler\\scheduler.conf")
class DebouncedHandler(FileSystemEventHandler):
    def __init__(self, callback_func, intervalo_segundos=2.0):
        super().__init__()
        self.callback_func = callback_func
        self.intervalo_segundos = intervalo_segundos
        self.ultima_execucao = 0
    def _tratar_evento(self, event):
        if event.is_directory:
            return
        agora = time.time()
        if agora - self.ultima_execucao < self.intervalo_segundos:
            return
        self.ultima_execucao = agora
        self.callback_func(event.event_type, event.src_path)
    def on_created(self, event):
        self._tratar_evento(event)
    def on_modified(self, event):
        self._tratar_evento(event)
    def on_deleted(self, event):
        self._tratar_evento(event)
def tratar_sinal_desligamento(signum, frame):
    observer.stop()
    parar_execucao.set()
signal.signal(signal.SIGTERM, tratar_sinal_desligamento)
signal.signal(signal.SIGINT, tratar_sinal_desligamento)
def executar_script(script_lines):
    script_content = "".join(script_lines)
    is_windows = platform.system() == "Windows"
    suffix = ".bat" if is_windows else ".sh"
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=suffix) as tmp:
        tmp.write(script_content)
        tmp_path = tmp.name
    try:
        if is_windows:
            subprocess.run([tmp_path], shell=True)
        else:
            os.chmod(tmp_path, 0o755)
            subprocess.run(["/bin/bash", tmp_path])
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
def carregar_configuracoes():
    config_file = get_configuration()
    debounce_time = 0.5
    actualization_time = 120
    if not config_file.exists():
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with config_file.open("w") as f:
            f.write("# Tempo em segundos para o intervalo do debounce e atualizações\n")
            f.write("debounce_time=0.5\n")
            f.write("actualization_time=120\n")
    for linha in config_file.read_text().splitlines():
        linha = linha.strip()
        if linha.startswith("debounce_time="):
            try:
                debounce_time = float(linha.split("=", 1)[1])
            except ValueError:
                pass
        elif linha.startswith("actualization_time="):
            try:
                actualization_time = int(linha.split("=", 1)[1])
            except ValueError:
                pass
    return debounce_time, actualization_time
def tarefa_principal_do_programa(tempo_atualizacao):
    while not parar_execucao.is_set():
        agora = datetime.now()
        with dados_lock:
            itens = list(dados.items())
        for caminho, (time_code, script, proxima_execucao) in itens:
            if agora >= proxima_execucao:
                executar_script(script)
                hora_de_execucao = croniter(time_code, datetime.now())
                nova_proxima = hora_de_execucao.get_next(datetime)
                with dados_lock:
                    if caminho in dados:
                        dados[caminho][2] = nova_proxima
        time.sleep(tempo_atualizacao)
def processar_ficheiro(tipo_evento, caminho_ficheiro):
    caminho_abs = os.path.abspath(caminho_ficheiro)
    try:
        with open(caminho_abs, "r") as k:
            conteudo = k.readlines()
        horas = datetime.now()
        if len(conteudo) > 2:
            time_code = conteudo[0].strip()
            script = conteudo[1:]
            hora_de_execucao = croniter(time_code, horas)
            proxima_execucao = hora_de_execucao.get_next(datetime)
            with dados_lock:
                dados[caminho_abs] = [time_code, script, proxima_execucao]
    except FileNotFoundError:
        pass
Pasta_Ficheiros = get_filesdir()
Pasta_Ficheiros.mkdir(parents=True, exist_ok=True)
debounce_time, actualization_time = carregar_configuracoes()
for arquivo in Pasta_Ficheiros.iterdir():
    if arquivo.is_file():
        processar_ficheiro("created", str(arquivo.resolve()))
handler = DebouncedHandler(callback_func=processar_ficheiro, intervalo_segundos=debounce_time)
observer = Observer()
observer.schedule(handler, path=Pasta_Ficheiros, recursive=False)
observer.start()
thread_app = threading.Thread(target=tarefa_principal_do_programa, args=(actualization_time), daemon=True)
thread_app.start()
parar_execucao.wait()
observer.join()