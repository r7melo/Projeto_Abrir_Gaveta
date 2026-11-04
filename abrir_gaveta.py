"""
Abrir Gaveta PDV

Uso:
  - Abrir o programa            -> abre a gaveta.
  - Abrir segurando SHIFT       -> abre o menu de configurações.
  - Primeira execução           -> abre o menu de configurações sozinho.
  - Tecla de atalho (opcional)  -> com o atalho ativo (ex.: Ctrl+Alt+Space), o programa
                                   fica em segundo plano, com um ícone perto do relógio,
                                   e abre a gaveta de qualquer tela.

Configurações:
  - Impressora conectada à gaveta.
  - Código de abertura (ESC/POS). O padrão nunca é apagado: só é trocado se
    "Editar código" estiver marcado. Ao desmarcar, o padrão volta.
  - Tecla de atalho.

Parâmetros: --configurar (menu), --residente (segundo plano).
"""
import os
import re
import sys
import json
import ctypes
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox

import win32api
import win32con
import win32gui
import win32print

APP_PASTA = "Gaveta"
TITULO = "Abrir Gaveta PDV"

# Código padrão (ESC/POS, EPSON/ELGIN): ESC p 0 25 250. Nunca é alterado.
CODIGO_PADRAO = bytes([0x1B, 0x70, 0x00, 0x19, 0xFA])

MB_YESNO = 0x04
MB_ICONERROR = 0x10
MB_ICONQUESTION = 0x20
IDYES = 6
VK_SHIFT = 0x10
ERRO_JA_EXISTE = 183

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
ORDEM_MODIFICADORES = [("Ctrl", MOD_CONTROL), ("Alt", MOD_ALT), ("Shift", MOD_SHIFT), ("Win", MOD_WIN)]
TECLAS_NOMEADAS = {
    "Space": 0x20, "Enter": 0x0D, "Tab": 0x09, "Insert": 0x2D, "Delete": 0x2E,
    "Home": 0x24, "End": 0x23, "PageUp": 0x21, "PageDown": 0x22,
    "Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28,
}
NOME_MUTEX = "Local\\AbrirGavetaPDV_Residente"
EXE_PRINCIPAL = "abrir_gaveta.exe"


# ------------------------------------------------------------------ código de abertura

def bytes_para_hex(dados):
    return " ".join(f"{b:02X}" for b in dados)


CODIGO_PADRAO_HEX = bytes_para_hex(CODIGO_PADRAO)


def hex_para_bytes(texto):
    """Converte '1B 70 00 19 FA' (ou 0x1B,0x70...) em bytes. Lança ValueError se inválido."""
    limpo = texto.replace("0x", "").replace("0X", "").replace("\\x", "").replace("\\X", "")
    limpo = "".join(limpo.replace(",", " ").replace(";", " ").replace("-", " ").split())
    if not limpo:
        raise ValueError("Digite o código em hexadecimal (ex.: 1B 70 00 19 FA).")
    if any(c not in "0123456789abcdefABCDEF" for c in limpo):
        raise ValueError("Use apenas números e letras de A a F (hexadecimal).")
    if len(limpo) % 2:
        raise ValueError("Cada byte precisa de 2 caracteres (ex.: 1B 70 00 19 FA).")
    dados = bytes(int(limpo[i:i + 2], 16) for i in range(0, len(limpo), 2))
    if len(dados) > 32:
        raise ValueError("O código pode ter no máximo 32 bytes.")
    return dados


# ------------------------------------------------------------------ tecla de atalho

def lista_de_teclas():
    letras = [chr(c) for c in range(ord("A"), ord("Z") + 1)]
    digitos = [str(n) for n in range(10)]
    funcoes = [f"F{n}" for n in range(1, 13)]
    return ["Space", "Enter"] + letras + digitos + funcoes + [
        "Tab", "Insert", "Delete", "Home", "End", "PageUp", "PageDown", "Up", "Down", "Left", "Right"]


def codigo_da_tecla(nome):
    """Retorna (codigo_virtual, nome_padrao) da tecla. Lança ValueError se não suportada."""
    n = nome.strip()
    if not n:
        raise ValueError("Escolha a tecla do atalho.")
    for canonico, vk in TECLAS_NOMEADAS.items():
        if canonico.upper() == n.upper():
            return vk, canonico
    u = n.upper()
    if len(u) == 1 and ("A" <= u <= "Z" or "0" <= u <= "9"):
        return ord(u), u
    if re.fullmatch(r"F\d{1,2}", u) and 1 <= int(u[1:]) <= 24:
        return 0x70 + int(u[1:]) - 1, f"F{int(u[1:])}"
    raise ValueError(f"Tecla não suportada: {nome}")


def atalho_para_codigos(texto):
    """'Ctrl+Alt+Space' -> (modificadores, codigo_virtual, texto_padrao). ValueError se inválido."""
    partes = [p.strip() for p in str(texto).split("+") if p.strip()]
    if not partes:
        raise ValueError("Escolha a tecla do atalho.")
    *nomes_mod, nome_tecla = partes
    mods = 0
    for nome in nomes_mod:
        u = nome.upper().replace("CONTROL", "CTRL")
        achou = next((m for r, m in ORDEM_MODIFICADORES if r.upper() == u), None)
        if achou is None:
            raise ValueError(f"Tecla modificadora inválida: {nome}")
        mods |= achou
    vk, canonico = codigo_da_tecla(nome_tecla)
    eh_funcao = bool(re.fullmatch(r"F\d{1,2}", canonico))
    if not eh_funcao and not (mods & ~MOD_SHIFT):
        raise ValueError("Marque Ctrl, Alt ou Win junto com a tecla (ou use uma tecla de F1 a F12).")
    nomes = [r for r, m in ORDEM_MODIFICADORES if mods & m]
    return mods, vk, "+".join(nomes + [canonico])


# ------------------------------------------------------------------ configuração

def caminho_config():
    """Config do usuário em %LOCALAPPDATA%\\Gaveta (gravável, inclusive em MSIX)."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_PASTA, "gaveta.config")


def mtime_config():
    try:
        return os.path.getmtime(caminho_config())
    except OSError:
        return 0


def pasta_programa():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def pasta_recursos():
    return getattr(sys, '_MEIPASS', pasta_programa())


def ler_config():
    """Retorna {'impressora': str, 'codigo': str|None, 'atalho': str|None}."""
    cfg = {"impressora": "", "codigo": None, "atalho": None}
    try:
        with open(caminho_config(), "r", encoding="utf-8") as f:
            bruto = f.read().strip()
    except Exception:
        return cfg
    if not bruto:
        return cfg
    if not bruto.startswith("{"):
        cfg["impressora"] = bruto  # formato antigo: só o nome da impressora
        return cfg
    try:
        dados = json.loads(bruto)
    except Exception:
        return cfg
    cfg["impressora"] = str(dados.get("impressora", "")).strip()
    if dados.get("codigo"):
        try:
            hex_para_bytes(str(dados["codigo"]))
            cfg["codigo"] = str(dados["codigo"])
        except ValueError:
            pass
    if dados.get("atalho"):
        try:
            cfg["atalho"] = atalho_para_codigos(dados["atalho"])[2]
        except ValueError:
            pass
    return cfg


def salvar_config(impressora, codigo_hex=None, atalho=None):
    """Salva impressora, código personalizado (None = padrão) e atalho (None = desligado)."""
    caminho = caminho_config()
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    dados = {"impressora": impressora.strip()}
    if codigo_hex:
        dados["codigo"] = codigo_hex
    if atalho:
        dados["atalho"] = atalho
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)


def codigo_ativo(cfg):
    if cfg.get("codigo"):
        try:
            return hex_para_bytes(cfg["codigo"])
        except ValueError:
            pass
    return CODIGO_PADRAO


# ------------------------------------------------------------------ utilitários

def caixa_erro(texto):
    ctypes.windll.user32.MessageBoxW(0, texto, TITULO, MB_ICONERROR)


def caixa_sim_nao(texto):
    resp = ctypes.windll.user32.MessageBoxW(0, texto, TITULO, MB_YESNO | MB_ICONQUESTION)
    return resp == IDYES


def shift_pressionado():
    return bool(ctypes.windll.user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)


def em_segundo_plano(funcao, *args):
    threading.Thread(target=funcao, args=args, daemon=True).start()


def comando_do_programa(*args):
    """Comando para abrir o próprio programa de novo (sempre o executável principal)."""
    if getattr(sys, 'frozen', False):
        principal = os.path.join(pasta_programa(), EXE_PRINCIPAL)
        base = [principal if os.path.exists(principal) else sys.executable]
    else:
        base = [sys.executable.replace("python.exe", "pythonw.exe"), os.path.abspath(__file__)]
    return base + list(args)


def lancar(*args):
    """Abre outra cópia do programa, separada, sem janela de console."""
    try:
        subprocess.Popen(comando_do_programa(*args),
                         creationflags=0x00000008 | 0x08000000,  # DETACHED_PROCESS | CREATE_NO_WINDOW
                         close_fds=True)
    except Exception as e:
        caixa_erro(f"Não foi possível abrir o programa.\n\n{e}")


# ------------------------------------------------------------------ impressoras

def listar_impressoras():
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    try:
        return sorted({p[2] for p in win32print.EnumPrinters(flags, None, 1)})
    except Exception:
        return []


def enviar_comando(nome_impressora, codigo=CODIGO_PADRAO):
    """Envia o código da gaveta em modo RAW. Lança exceção se falhar."""
    handle = win32print.OpenPrinter(nome_impressora)
    try:
        win32print.StartDocPrinter(handle, 1, ("Abrir Gaveta", None, "RAW"))
        try:
            win32print.StartPagePrinter(handle)
            win32print.WritePrinter(handle, codigo)
            win32print.EndPagePrinter(handle)
        finally:
            win32print.EndDocPrinter(handle)
    finally:
        win32print.ClosePrinter(handle)


# ------------------------------------------------------------------ MENU DE CONFIGURAÇÕES

def modo_configuracao():
    """Abre o menu de configurações. Retorna True se o usuário salvou."""
    impressoras = listar_impressoras()
    cfg = ler_config()
    resultado = {"salvo": False}

    janela = tk.Tk()
    janela.title(f"{TITULO} - Configurações")
    janela.resizable(False, False)
    try:
        janela.iconbitmap(os.path.join(pasta_recursos(), "icon-open-drawer.ico"))
    except Exception:
        pass

    negrito = ("Segoe UI", 10, "bold")
    pequeno = ("Segoe UI", 8)
    cinza = "#64748B"

    frame = ttk.Frame(janela, padding=20)
    frame.grid(row=0, column=0)
    frame.columnconfigure(0, weight=1)

    # --- Impressora ---------------------------------------------------------
    ttk.Label(frame, text="Impressora conectada à gaveta", font=negrito).grid(
        row=0, column=0, columnspan=3, sticky="w")

    if cfg["impressora"] in impressoras:
        inicial = cfg["impressora"]  # a já salva, se ainda existir na lista
    elif impressoras:
        inicial = impressoras[0]  # senão, a primeira da lista
    else:
        inicial = cfg["impressora"]

    escolha = tk.StringVar(value=inicial)
    ttk.Combobox(frame, textvariable=escolha, values=impressoras, width=50).grid(
        row=1, column=0, columnspan=3, pady=(8, 4), sticky="ew")

    dica = ("Escolha na lista ou digite o nome exato da impressora (ex.: ELGIN i8)."
            if impressoras else
            "Nenhuma impressora encontrada. Instale a impressora ou digite o nome exato.")
    ttk.Label(frame, text=dica, foreground=cinza, font=pequeno).grid(
        row=2, column=0, columnspan=3, sticky="w")

    # --- Código de abertura ---------------------------------------------------
    ttk.Separator(frame).grid(row=3, column=0, columnspan=3, sticky="ew", pady=14)
    ttk.Label(frame, text="Código de abertura da gaveta", font=negrito).grid(
        row=4, column=0, columnspan=3, sticky="w")

    editar = tk.BooleanVar(value=bool(cfg["codigo"]))
    codigo_var = tk.StringVar(value=cfg["codigo"] or CODIGO_PADRAO_HEX)
    entrada = ttk.Entry(frame, textvariable=codigo_var, width=50)

    def alternar_edicao():
        if editar.get():
            entrada.config(state="normal")
            entrada.focus_set()
            entrada.icursor("end")
        else:
            codigo_var.set(CODIGO_PADRAO_HEX)  # desmarcou: volta ao padrão
            entrada.config(state="disabled")

    ttk.Checkbutton(frame, text="Editar código (avançado)", variable=editar,
                    command=alternar_edicao).grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 4))
    entrada.grid(row=6, column=0, columnspan=3, sticky="ew")
    entrada.config(state="normal" if editar.get() else "disabled")

    ttk.Label(frame,
              text=f"Padrão: {CODIGO_PADRAO_HEX} (ESC p 0 25 250). Ao desmarcar, o padrão volta.",
              foreground=cinza, font=pequeno).grid(row=7, column=0, columnspan=3, sticky="w", pady=(4, 0))

    # --- Tecla de atalho ------------------------------------------------------
    ttk.Separator(frame).grid(row=8, column=0, columnspan=3, sticky="ew", pady=14)
    ttk.Label(frame, text="Tecla de atalho", font=negrito).grid(
        row=9, column=0, columnspan=3, sticky="w")

    ativar = tk.BooleanVar(value=bool(cfg["atalho"]))
    if cfg["atalho"]:
        partes = cfg["atalho"].split("+")
        marcadas, tecla_inicial = set(partes[:-1]), partes[-1]
    else:
        marcadas, tecla_inicial = {"Ctrl", "Alt"}, "Space"
    var_mod = {nome: tk.BooleanVar(value=nome in marcadas) for nome, _ in ORDEM_MODIFICADORES}
    var_tecla = tk.StringVar(value=tecla_inicial)
    previa = tk.StringVar()

    ttk.Checkbutton(frame, text="Abrir a gaveta com uma tecla de atalho", variable=ativar,
                    command=lambda: atualizar_atalho()).grid(row=10, column=0, columnspan=3, sticky="w", pady=(8, 4))

    linha = ttk.Frame(frame)
    linha.grid(row=11, column=0, columnspan=3, sticky="w")
    controles = []
    for coluna, (nome, _) in enumerate(ORDEM_MODIFICADORES):
        cb = ttk.Checkbutton(linha, text=nome, variable=var_mod[nome], command=lambda: atualizar_atalho())
        cb.grid(row=0, column=coluna, padx=(0, 10))
        controles.append(cb)
    combo_tecla = ttk.Combobox(linha, textvariable=var_tecla, values=lista_de_teclas(),
                               width=10, state="readonly")
    combo_tecla.grid(row=0, column=len(ORDEM_MODIFICADORES), padx=(6, 0))
    combo_tecla.bind("<<ComboboxSelected>>", lambda e: atualizar_atalho())

    ttk.Label(frame, textvariable=previa, font=("Segoe UI", 9, "bold")).grid(
        row=12, column=0, columnspan=3, sticky="w", pady=(6, 0))
    ttk.Label(frame,
              text="Com o atalho ativo, o programa fica em segundo plano (ícone perto do relógio)\n"
                   "e abre a gaveta de qualquer tela.",
              foreground=cinza, font=pequeno, justify="left").grid(
        row=13, column=0, columnspan=3, sticky="w", pady=(2, 0))

    def montar_atalho():
        nomes = [nome for nome, _ in ORDEM_MODIFICADORES if var_mod[nome].get()]
        return "+".join(nomes + [var_tecla.get()])

    def atualizar_atalho():
        estado = "normal" if ativar.get() else "disabled"
        for cb in controles:
            cb.config(state=estado)
        combo_tecla.config(state="readonly" if ativar.get() else "disabled")
        if not ativar.get():
            previa.set("Atalho desligado")
            return
        try:
            previa.set(f"Atalho: {atalho_para_codigos(montar_atalho())[2]}")
        except ValueError as e:
            previa.set(str(e))

    def abrir_inicializacao():
        try:
            os.startfile("ms-settings:startupapps")
        except Exception as e:
            messagebox.showerror(TITULO, f"Não foi possível abrir as configurações do Windows.\n\n{e}",
                                 parent=janela)

    ttk.Button(frame, text="Iniciar junto com o Windows...", command=abrir_inicializacao).grid(
        row=14, column=0, columnspan=3, sticky="w", pady=(8, 0))
    ttk.Label(frame, text="Abre Configurações > Aplicativos > Inicialização. Ative \"Abrir Gaveta PDV\".",
              foreground=cinza, font=pequeno).grid(row=15, column=0, columnspan=3, sticky="w", pady=(2, 0))

    atualizar_atalho()

    # --- Botões ---------------------------------------------------------------
    ttk.Separator(frame).grid(row=16, column=0, columnspan=3, sticky="ew", pady=14)

    def ler_formulario():
        """Valida o formulário. Retorna (impressora, codigo, codigo_hex, atalho) ou None."""
        nome = escolha.get().strip()
        if not nome:
            messagebox.showwarning(TITULO, "Selecione ou digite o nome da impressora.", parent=janela)
            return None
        codigo, codigo_hex = CODIGO_PADRAO, None
        if editar.get():
            try:
                codigo = hex_para_bytes(codigo_var.get())
            except ValueError as e:
                messagebox.showwarning(TITULO, str(e), parent=janela)
                return None
            if codigo != CODIGO_PADRAO:
                codigo_hex = bytes_para_hex(codigo)
        atalho = None
        if ativar.get():
            try:
                atalho = atalho_para_codigos(montar_atalho())[2]
            except ValueError as e:
                messagebox.showwarning(TITULO, str(e), parent=janela)
                return None
        return nome, codigo, codigo_hex, atalho

    def testar():
        dados = ler_formulario()
        if not dados:
            return
        nome, codigo = dados[0], dados[1]
        try:
            enviar_comando(nome, codigo)
        except Exception as e:
            messagebox.showerror(TITULO, f"Não foi possível abrir a gaveta.\n\n"
                                         f"Impressora: '{nome}'\nErro: {e}", parent=janela)

    def salvar():
        dados = ler_formulario()
        if not dados:
            return
        nome, _, codigo_hex, atalho = dados
        try:
            salvar_config(nome, codigo_hex, atalho)
        except Exception as e:
            messagebox.showerror(TITULO, f"Não foi possível salvar a configuração.\n\n{e}", parent=janela)
            return
        resultado["salvo"] = True
        janela.destroy()

    ttk.Button(frame, text="Testar gaveta", command=testar).grid(row=17, column=0, sticky="w")
    ttk.Button(frame, text="Salvar", command=salvar).grid(row=17, column=1, sticky="e", padx=(0, 8))
    ttk.Button(frame, text="Cancelar", command=janela.destroy).grid(row=17, column=2, sticky="e")

    janela.update_idletasks()
    x = (janela.winfo_screenwidth() - janela.winfo_width()) // 2
    y = (janela.winfo_screenheight() - janela.winfo_height()) // 3
    janela.geometry(f"+{x}+{y}")
    janela.mainloop()
    return resultado["salvo"]


# ------------------------------------------------------------------ SEGUNDO PLANO (tecla de atalho)

def _kernel32():
    return ctypes.WinDLL("kernel32", use_last_error=True)


def residente_ativo():
    """Já existe uma cópia do programa em segundo plano?"""
    k = _kernel32()
    k.OpenMutexW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
    k.OpenMutexW.restype = ctypes.c_void_p
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = k.OpenMutexW(0x00100000, False, NOME_MUTEX)  # SYNCHRONIZE
    if handle:
        k.CloseHandle(handle)
        return True
    return False


def _criar_mutex_residente():
    """Reserva o 'direito' de ser a única cópia em segundo plano. None se já existe outra."""
    k = _kernel32()
    k.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    k.CreateMutexW.restype = ctypes.c_void_p
    handle = k.CreateMutexW(None, False, NOME_MUTEX)
    if not handle or ctypes.get_last_error() == ERRO_JA_EXISTE:
        return None
    return handle


def abrir_gaveta_agora():
    """Abre a gaveta (usado pela tecla de atalho e pelo menu da bandeja)."""
    cfg = ler_config()
    if not cfg["impressora"]:
        lancar("--configurar")
        return
    try:
        enviar_comando(cfg["impressora"], codigo_ativo(cfg))
    except Exception as e:
        caixa_erro(f"Não foi possível abrir a gaveta.\n\n"
                   f"Impressora configurada: '{cfg['impressora']}'\nErro: {e}")


WM_BANDEJA = win32con.WM_USER + 20
ID_ABRIR, ID_CONFIG, ID_SAIR = 1001, 1002, 1003
ID_ATALHO, ID_TIMER = 1, 1


class Residente:
    """Janela invisível + ícone na bandeja + tecla de atalho global."""

    def __init__(self):
        self.mtime = None
        self.dica = TITULO
        self.msg_barra = win32gui.RegisterWindowMessage("TaskbarCreated")
        mapa = {
            win32con.WM_DESTROY: self.ao_destruir,
            win32con.WM_COMMAND: self.ao_comando,
            win32con.WM_HOTKEY: self.ao_atalho,
            win32con.WM_TIMER: self.ao_timer,
            WM_BANDEJA: self.ao_bandeja,
            self.msg_barra: self.ao_barra_recriada,
        }
        classe = win32gui.WNDCLASS()
        classe.hInstance = win32api.GetModuleHandle(None)
        classe.lpszClassName = "AbrirGavetaResidente"
        classe.lpfnWndProc = mapa
        atom = win32gui.RegisterClass(classe)
        self.hwnd = win32gui.CreateWindow(atom, TITULO, 0, 0, 0, 0, 0, 0, 0, classe.hInstance, None)
        self.icone = self._carregar_icone()
        self._bandeja(win32gui.NIM_ADD)
        ctypes.windll.user32.SetTimer(self.hwnd, ID_TIMER, 1000, None)
        self.recarregar()

    # -- ícone e menu da bandeja
    def _carregar_icone(self):
        try:
            return win32gui.LoadImage(0, os.path.join(pasta_recursos(), "icon-open-drawer.ico"),
                                      win32con.IMAGE_ICON, 0, 0,
                                      win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE)
        except Exception:
            return win32gui.LoadIcon(0, win32con.IDI_APPLICATION)

    def _bandeja(self, acao):
        sinalizadores = win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP
        try:
            win32gui.Shell_NotifyIcon(acao, (self.hwnd, 0, sinalizadores, WM_BANDEJA, self.icone, self.dica))
        except Exception:
            pass

    def ao_barra_recriada(self, hwnd, msg, wparam, lparam):
        self._bandeja(win32gui.NIM_ADD)  # o Explorer reiniciou: recoloca o ícone
        return 0

    def ao_bandeja(self, hwnd, msg, wparam, lparam):
        if lparam == win32con.WM_LBUTTONDBLCLK:
            em_segundo_plano(abrir_gaveta_agora)
        elif lparam == win32con.WM_RBUTTONUP:
            self._menu()
        return 0

    def _menu(self):
        menu = win32gui.CreatePopupMenu()
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_ABRIR, "Abrir gaveta")
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_CONFIG, "Configurações")
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_SAIR, "Sair")
        x, y = win32gui.GetCursorPos()
        win32gui.SetForegroundWindow(self.hwnd)
        win32gui.TrackPopupMenu(menu, win32con.TPM_LEFTALIGN | win32con.TPM_RIGHTBUTTON, x, y, 0, self.hwnd, None)
        win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)
        win32gui.DestroyMenu(menu)

    def ao_comando(self, hwnd, msg, wparam, lparam):
        comando = win32api.LOWORD(wparam)
        if comando == ID_ABRIR:
            em_segundo_plano(abrir_gaveta_agora)
        elif comando == ID_CONFIG:
            lancar("--configurar")
        elif comando == ID_SAIR:
            win32gui.DestroyWindow(self.hwnd)
        return 0

    # -- tecla de atalho
    def ao_atalho(self, hwnd, msg, wparam, lparam):
        em_segundo_plano(abrir_gaveta_agora)
        return 0

    def ao_timer(self, hwnd, msg, wparam, lparam):
        if mtime_config() != self.mtime:  # as configurações mudaram
            self.recarregar()
        return 0

    def recarregar(self):
        self.mtime = mtime_config()
        cfg = ler_config()
        try:
            win32gui.UnregisterHotKey(self.hwnd, ID_ATALHO)
        except Exception:
            pass
        if not cfg["atalho"]:  # atalho desligado: não há mais motivo para ficar aberto
            win32gui.DestroyWindow(self.hwnd)
            return
        mods, vk, texto = atalho_para_codigos(cfg["atalho"])
        try:
            win32gui.RegisterHotKey(self.hwnd, ID_ATALHO, mods | MOD_NOREPEAT, vk)
            self.dica = f"{TITULO} ({texto})"
        except Exception:
            self.dica = TITULO
            em_segundo_plano(caixa_erro,
                             f"Não foi possível ativar a tecla de atalho {texto}.\n\n"
                             f"Ela pode estar em uso por outro programa. "
                             f"Abra as configurações e escolha outra combinação.")
        self._bandeja(win32gui.NIM_MODIFY)

    def ao_destruir(self, hwnd, msg, wparam, lparam):
        try:
            win32gui.UnregisterHotKey(self.hwnd, ID_ATALHO)
            ctypes.windll.user32.KillTimer(self.hwnd, ID_TIMER)
        except Exception:
            pass
        self._bandeja(win32gui.NIM_DELETE)
        win32gui.PostQuitMessage(0)
        return 0


_mutex_residente = None  # mantém a reserva enquanto o programa roda


def modo_residente():
    """Fica em segundo plano ouvindo a tecla de atalho. Sai se o atalho for desligado."""
    global _mutex_residente
    if not ler_config()["atalho"]:
        return
    _mutex_residente = _criar_mutex_residente()
    if _mutex_residente is None:  # já existe outra cópia em segundo plano
        return
    Residente()
    win32gui.PumpMessages()


def garantir_residente():
    """Se o atalho estiver ativo e nada estiver ouvindo, inicia o segundo plano."""
    if ler_config()["atalho"] and not residente_ativo():
        lancar("--residente")


# ------------------------------------------------------------------ ABRIR GAVETA

def modo_abrir_gaveta():
    cfg = ler_config()

    # Primeira execução: ainda não há impressora configurada.
    if not cfg["impressora"]:
        if not modo_configuracao():
            return
        cfg = ler_config()

    try:
        enviar_comando(cfg["impressora"], codigo_ativo(cfg))
    except Exception as e:
        pergunta = (f"Não foi possível abrir a gaveta.\n\n"
                    f"Impressora configurada: '{cfg['impressora']}'\nErro: {e}\n\n"
                    f"Deseja alterar as configurações?")
        if caixa_sim_nao(pergunta) and modo_configuracao():
            cfg = ler_config()
            try:
                enviar_comando(cfg["impressora"], codigo_ativo(cfg))
            except Exception as e2:
                caixa_erro(f"Não foi possível abrir a gaveta.\n\n"
                           f"Impressora: '{cfg['impressora']}'\nErro: {e2}")

    # Com a tecla de atalho ativa, esta cópia continua em segundo plano.
    if ler_config()["atalho"] and not residente_ativo():
        modo_residente()


# ------------------------------------------------------------------ main

def eh_executavel_de_inicio():
    """O gaveta_inicio.exe é o que o Windows abre ao iniciar (só segundo plano, sem abrir a gaveta)."""
    return getattr(sys, 'frozen', False) and "inicio" in os.path.basename(sys.executable).lower()


def configurar_e_garantir_residente():
    if modo_configuracao():
        garantir_residente()


def main():
    if "--configurar" in sys.argv:
        configurar_e_garantir_residente()
    elif "--residente" in sys.argv or eh_executavel_de_inicio():
        modo_residente()
    elif shift_pressionado():
        configurar_e_garantir_residente()
    else:
        modo_abrir_gaveta()


if __name__ == '__main__':
    main()