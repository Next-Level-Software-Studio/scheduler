from pathlib import Path
from datetime import datetime
import platform, os, time, threading, signal, subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from croniter import croniter
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
dados = {}
parar_execucao = threading.Event()
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
def tarefa_principal_do_programa():
    with open(get_configuration(), "r") as f:
        for linha in f:
            if linha.startswith("actualization_time="):
                tempo_atualizacao = int(linha.split("actualization_time=")[1])
                break
        else:
            tempo_atualizacao = 120
    while not parar_execucao.is_set():
        for i in dados:
            time_code, script, proxima_execucao = dados[i]
            if datetime.now() >= proxima_execucao:
                subprocess.run("".join(script), shell=True)
                hora_de_execucao = croniter(time_code, datetime.now())
                proxima_execucao = hora_de_execucao.get_next(datetime)
                dados[i][2] = proxima_execucao
        time.sleep(tempo_atualizacao)
Pasta_Ficheiros = get_filesdir()
Pasta_Ficheiros.mkdir(parents=True, exist_ok=True)
configuration_file = get_configuration()
if not configuration_file.exists():
    configuration_file.touch()
    with configuration_file.open("w") as f:
        f.write("# time must be written in seconds\n")
        f.write("#debounce_time=0.5\n")
        f.write("#actualization_time=120\n")
debounce_time = 0.5
for i in get_configuration().read_text().splitlines():
    if i.startswith("debounce_time="):
        debounce_time = float(i.split("debounce_time=")[1])
    else:
        continue
for arquivo in Pasta_Ficheiros.iterdir():
    if arquivo.is_file():
        with arquivo.open("r") as f:
            content = f.readlines()
        if len(content) < 2:
            continue
        horas = datetime.now()
        time_code = content[0].strip()
        script = content[1:]
        hora_de_execucao = croniter(time_code, horas)
        proxima_execucao = hora_de_execucao.get_next(datetime)
        dados[str(arquivo.resolve())] = [time_code, script, proxima_execucao]
def processar_ficheiro(tipo_evento, caminho_ficheiro):
    caminho_abs = os.path.abspath(caminho_ficheiro)
    try:
        with open(caminho_abs, "r") as k:
            conteudo = k.readlines()
        if len(conteudo) < 2:
            return
        elif len(conteudo) >= 2:
            horas = datetime.now()
            time_code = conteudo[0].strip()
            script = conteudo[1:]
            hora_de_execucao = croniter(time_code, horas)
            proxima_execucao = hora_de_execucao.get_next(datetime)
            dados[str(caminho_abs)] = [time_code, script, proxima_execucao]
    except FileNotFoundError:
        if caminho_abs in dados:
            del dados[caminho_abs]
handler = DebouncedHandler(callback_func=processar_ficheiro, intervalo_segundos=debounce_time)
observer = Observer()
observer.schedule(handler, path=Pasta_Ficheiros, recursive=False)
observer.start()
thread_app = threading.Thread(target=tarefa_principal_do_programa, daemon=True)
thread_app.start()
parar_execucao.wait()
observer.join()