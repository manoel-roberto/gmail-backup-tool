import os
import sys
import base64

if getattr(sys, 'frozen', False):
    self_dir = os.path.dirname(os.path.abspath(sys.executable))
else:
    self_dir = os.path.dirname(os.path.abspath(__file__))

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from google.api_core.exceptions import GoogleAPIError
from googleapiclient.discovery import build
import json
import email
from email.header import decode_header

# Escopo necessário para ler e apagar os e-mails
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

# Arquivo padrão de credenciais da aplicação (credentials.json do Google Cloud)
DEFAULT_CREDENTIALS_FILE = os.path.join(self_dir, "credentials.json")
DEFAULT_TOKEN_FILE = os.path.join(self_dir, "credencial.json")

NOME_LABELS_SISTEMA = {
    'INBOX': 'Caixa de Entrada',
    'SENT': 'Enviados',
    'DRAFT': 'Rascunhos',
    'TRASH': 'Lixeira',
    'SPAM': 'Spam',
    'STARRED': 'Com Estrela'
}

LABELS_IGNORAR = {
    'IMPORTANT', 'UNREAD', 'CHAT', 'CATEGORY_PERSONAL', 
    'CATEGORY_UPDATES', 'CATEGORY_PROMOTIONS', 
    'CATEGORY_SOCIAL', 'CATEGORY_FORUMS'
}

def sanitizar_nome_pasta(nome):
    """Sanitiza nomes de marcadores para criar pastas seguras no sistema de arquivos."""
    if not nome:
        return 'Outros'
    import re
    nome_limpo = re.sub(r'[\x00-\x1f\\:*?"<>|]', '_', nome).strip()
    partes = [p.strip() for p in nome_limpo.split('/') if p.strip()]
    return os.path.join(*partes) if partes else 'Outros'

def sanitizar_nome_arquivo(nome, max_chars=140):
    """Gera um nome de arquivo seguro a partir do assunto do e-mail."""
    if not nome:
        return 'Sem assunto'
    import re
    nome_limpo = re.sub(r'[\r\n\t\x00-\x1f]+', ' ', nome)
    nome_limpo = re.sub(r':\s*', ' - ', nome_limpo)
    nome_limpo = re.sub(r'[\\/*?\"<>|]', '_', nome_limpo)
    nome_limpo = re.sub(r'\s+', ' ', nome_limpo)
    nome_limpo = re.sub(r'(- )+', '- ', nome_limpo)
    nome_limpo = re.sub(r'_+', '_', nome_limpo)
    nome_limpo = nome_limpo.strip(' .-_')
    if not nome_limpo:
        nome_limpo = 'Sem assunto'
    if len(nome_limpo) > max_chars:
        nome_limpo = nome_limpo[:max_chars].rstrip(' .-_')
    return nome_limpo

def extrair_assunto_email(msg_bytes):
    """Extrai e decodifica o assunto (Subject) da mensagem RFC 822."""
    try:
        msg = email.message_from_bytes(msg_bytes)
        subject_raw = msg.get('Subject', '')
        if not subject_raw:
            return "Sem assunto"
        partes = decode_header(subject_raw)
        texto = []
        for p, enc in partes:
            if isinstance(p, bytes):
                texto.append(p.decode(enc or 'utf-8', errors='replace'))
            else:
                texto.append(str(p))
        assunto = ''.join(texto).strip()
        return assunto if assunto else "Sem assunto"
    except Exception:
        return "Sem assunto"

def criar_flow(client_secrets_file=None):
    """Cria o fluxo de autorização OAuth usando o arquivo informado, credentials.json ou variáveis de ambiente."""
    candidatos = []
    if client_secrets_file:
        candidatos.append(client_secrets_file)
    candidatos.append(DEFAULT_CREDENTIALS_FILE)
    candidatos.append(os.path.join(os.getcwd(), "credentials.json"))
    candidatos.append(os.path.join(self_dir, "client_secret.json"))

    for arq in candidatos:
        if arq and os.path.exists(arq):
            try:
                return InstalledAppFlow.from_client_secrets_file(arq, SCOPES)
            except Exception:
                pass

    cid = os.getenv("GMAIL_CLIENT_ID")
    csecret = os.getenv("GMAIL_CLIENT_SECRET")
    if cid and csecret:
        cfg = {
            "installed": {
                "client_id": cid,
                "client_secret": csecret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"]
            }
        }
        return InstalledAppFlow.from_client_config(cfg, SCOPES)

    raise FileNotFoundError(
        "Arquivo de credenciais 'credentials.json' não encontrado na pasta da aplicação "
        "e variáveis de ambiente GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET não foram definidas.\n"
        "Baixe o arquivo de credenciais OAuth no Google Cloud Console e coloque-o ao lado do aplicativo."
    )

def obter_servico_gmail(client_secrets_file=None, token_file=DEFAULT_TOKEN_FILE, forcar_login=False, log_callback=print):
    creds = None
    is_service_account = False
    
    # Se não forçamos um novo login, tenta carregar o token salvo anteriormente
    if not forcar_login and token_file and os.path.exists(token_file):
        try:
            with open(token_file, 'r') as f:
                data = json.load(f)
            if data.get('type') == 'service_account':
                creds = service_account.Credentials.from_service_account_file(token_file, scopes=SCOPES)
                is_service_account = True
            else:
                creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        except Exception as e:
            log_callback(f"Aviso ao ler token existente: {e}")
            creds = None
        
    # Somente tenta o fluxo OAuth se não for Service Account
    if not is_service_account:
        if creds and hasattr(creds, 'expired') and creds.expired and hasattr(creds, 'refresh_token') and creds.refresh_token and not forcar_login:
            try:
                creds.refresh(Request())
                if token_file:
                    with open(token_file, 'w') as token:
                        token.write(creds.to_json())
            except Exception as e:
                log_callback(f"Token expirado não pôde ser renovado ({e}). Solicitando nova autorização...")
                creds = None

        if not creds or not getattr(creds, 'valid', False) or forcar_login:
            log_callback("Abrindo navegador para autorização da conta Google... (Selecione a conta desejada e autorize)")
            flow = criar_flow(client_secrets_file)
            creds = flow.run_local_server(
                port=0,
                prompt='select_account consent',
                access_type='offline'
            )
            if token_file:
                with open(token_file, 'w') as token:
                    token.write(creds.to_json())
                log_callback("Credenciais salvas com sucesso.")

    service = build('gmail', 'v1', credentials=creds)
    return service

def obter_info_conta_conectada(token_file=DEFAULT_TOKEN_FILE):
    """
    Retorna {'email': str, 'messagesTotal': int} se houver token válido salvo,
    ou None se não estiver autenticado (sem abrir navegador).
    """
    if not token_file or not os.path.exists(token_file):
        return None
    try:
        with open(token_file, 'r') as f:
            data = json.load(f)
        if data.get('type') == 'service_account':
            creds = service_account.Credentials.from_service_account_file(token_file, scopes=SCOPES)
        else:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
            
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(token_file, 'w') as f:
                    f.write(creds.to_json())
            else:
                return None
                
        service = build('gmail', 'v1', credentials=creds)
        profile = service.users().getProfile(userId='me').execute()
        return {
            'email': profile.get('emailAddress', 'Desconhecido'),
            'messagesTotal': profile.get('messagesTotal', 0)
        }
    except Exception:
        return None

def desconectar_conta(token_file=DEFAULT_TOKEN_FILE):
    """Remove o arquivo de token salvo."""
    if token_file and os.path.exists(token_file):
        try:
            os.remove(token_file)
            return True
        except Exception:
            return False
    return False

def obter_marcadores_conta(token_file=DEFAULT_TOKEN_FILE):
    """Retorna a lista de marcadores (labels) da conta conectada."""
    if not token_file or not os.path.exists(token_file):
        return []
    try:
        service = obter_servico_gmail(token_file=token_file)
        labels = service.users().labels().list(userId='me').execute().get('labels', [])
        return labels
    except Exception:
        return []

def obter_quantidade_emails_inbox(service):
    try:
        resultado = service.users().labels().get(userId='me', id='INBOX').execute()
        return resultado.get('messagesTotal', 0)
    except Exception as e:
        print(f"Erro ao obter quantidade de e-mails na INBOX: {e}")
        return 0

def consultar_primeiro_email(client_secrets_file=None, token_file=DEFAULT_TOKEN_FILE, log_callback=print, marcador='TODAS'):
    try:
        service = obter_servico_gmail(client_secrets_file, token_file, log_callback=log_callback)
        
        if isinstance(marcador, (list, tuple, set)):
            lista_marcadores = list(marcador)
        elif marcador and marcador != 'TODAS':
            lista_marcadores = [marcador]
        else:
            lista_marcadores = ['TODAS']

        try:
            todas_lbls = service.users().labels().list(userId='me').execute().get('labels', [])
            mapa = {l['id']: NOME_LABELS_SISTEMA.get(l['id'], l['name']) for l in todas_lbls}
        except Exception:
            mapa = {}

        candidatos = []

        if 'TODAS' in lista_marcadores:
            log_callback("Buscando o e-mail mais recente (Todas as Caixas)...")
            res = service.users().messages().list(userId='me', maxResults=1).execute()
            msgs = res.get('messages', [])
            if msgs:
                candidatos.append((msgs[0]['id'], 'Todas as Caixas'))
        else:
            nomes_sel = [mapa.get(m, NOME_LABELS_SISTEMA.get(m, m)) for m in lista_marcadores]
            log_callback(f"Buscando o e-mail mais recente entre as caixas selecionadas: {', '.join(nomes_sel)}...")
            for lid in lista_marcadores:
                kwargs = {'userId': 'me', 'maxResults': 1, 'labelIds': [lid]}
                if lid in ['TRASH', 'SPAM']:
                    kwargs['includeSpamTrash'] = True
                res = service.users().messages().list(**kwargs).execute()
                msgs = res.get('messages', [])
                if msgs:
                    nome_lbl = mapa.get(lid, NOME_LABELS_SISTEMA.get(lid, lid))
                    candidatos.append((msgs[0]['id'], nome_lbl))

        if not candidatos:
            log_callback("Nenhum e-mail encontrado nas caixas selecionadas.")
            return

        melhor_msg = None
        melhor_data_ts = -1
        melhor_origem = ""

        for msg_id, origem in candidatos:
            m = service.users().messages().get(
                userId='me', 
                id=msg_id, 
                format='metadata', 
                metadataHeaders=['Subject', 'From', 'Date']
            ).execute()
            ts = int(m.get('internalDate', 0))
            if ts > melhor_data_ts:
                melhor_data_ts = ts
                melhor_msg = m
                melhor_origem = origem

        if not melhor_msg:
            log_callback("Nenhum e-mail encontrado.")
            return

        headers = melhor_msg.get('payload', {}).get('headers', [])
        assunto = next((h['value'] for h in headers if h['name'] == 'Subject'), 'Sem assunto')
        remetente = next((h['value'] for h in headers if h['name'] == 'From'), 'Desconhecido')
        data_envio = next((h['value'] for h in headers if h['name'] == 'Date'), 'Data desconhecida')

        log_callback(f"\n--- Primeiro E-mail (Mais Recente) ---")
        log_callback(f"Caixa/Marcador: {melhor_origem}")
        log_callback(f"De: {remetente}")
        log_callback(f"Assunto: {assunto}")
        log_callback(f"Data: {data_envio}")
        log_callback(f"ID: {melhor_msg.get('id')}")
        log_callback(f"----------------------------------------\n")

    except GoogleAPIError as erro:
        log_callback(f"Ocorreu um erro na API do Gmail: {erro}")
    except Exception as e:
        log_callback(f"Ocorreu um erro inesperado: {e}")

def consultar_email_mais_antigo(client_secrets_file=None, token_file=DEFAULT_TOKEN_FILE, log_callback=print, marcador='TODAS'):
    try:
        service = obter_servico_gmail(client_secrets_file, token_file, log_callback=log_callback)

        if isinstance(marcador, (list, tuple, set)):
            lista_marcadores = list(marcador)
        elif marcador and marcador != 'TODAS':
            lista_marcadores = [marcador]
        else:
            lista_marcadores = ['TODAS']

        try:
            todas_lbls = service.users().labels().list(userId='me').execute().get('labels', [])
            mapa = {l['id']: NOME_LABELS_SISTEMA.get(l['id'], l['name']) for l in todas_lbls}
        except Exception:
            mapa = {}

        candidatos = []

        if 'TODAS' in lista_marcadores:
            log_callback("Buscando o e-mail mais antigo (Todas as Caixas)... (isso pode demorar um pouco)")
            page_token = None
            ultimo_id = None
            while True:
                kwargs = {'userId': 'me', 'maxResults': 500}
                if page_token:
                    kwargs['pageToken'] = page_token
                res = service.users().messages().list(**kwargs).execute()
                msgs = res.get('messages', [])
                if msgs:
                    ultimo_id = msgs[-1]['id']
                page_token = res.get('nextPageToken')
                if not page_token:
                    break
            if ultimo_id:
                candidatos.append((ultimo_id, 'Todas as Caixas'))
        else:
            nomes_sel = [mapa.get(m, NOME_LABELS_SISTEMA.get(m, m)) for m in lista_marcadores]
            log_callback(f"Buscando o e-mail mais antigo entre as caixas selecionadas: {', '.join(nomes_sel)}... (isso pode demorar um pouco)")
            for lid in lista_marcadores:
                nome_lbl = mapa.get(lid, NOME_LABELS_SISTEMA.get(lid, lid))
                page_token = None
                ultimo_id = None
                while True:
                    kwargs = {'userId': 'me', 'maxResults': 500, 'labelIds': [lid]}
                    if lid in ['TRASH', 'SPAM']:
                        kwargs['includeSpamTrash'] = True
                    if page_token:
                        kwargs['pageToken'] = page_token
                    res = service.users().messages().list(**kwargs).execute()
                    msgs = res.get('messages', [])
                    if msgs:
                        ultimo_id = msgs[-1]['id']
                    page_token = res.get('nextPageToken')
                    if not page_token:
                        break
                if ultimo_id:
                    candidatos.append((ultimo_id, nome_lbl))

        if not candidatos:
            log_callback("Nenhum e-mail encontrado nas caixas selecionadas.")
            return

        melhor_msg = None
        melhor_data_ts = float('inf')
        melhor_origem = ""

        for msg_id, origem in candidatos:
            m = service.users().messages().get(
                userId='me', 
                id=msg_id, 
                format='metadata', 
                metadataHeaders=['Subject', 'From', 'Date']
            ).execute()
            ts = int(m.get('internalDate', 0))
            if ts < melhor_data_ts:
                melhor_data_ts = ts
                melhor_msg = m
                melhor_origem = origem

        if not melhor_msg:
            log_callback("Nenhum e-mail encontrado.")
            return

        headers = melhor_msg.get('payload', {}).get('headers', [])
        assunto = next((h['value'] for h in headers if h['name'] == 'Subject'), 'Sem assunto')
        remetente = next((h['value'] for h in headers if h['name'] == 'From'), 'Desconhecido')
        data_envio = next((h['value'] for h in headers if h['name'] == 'Date'), 'Data desconhecida')

        log_callback(f"\n--- E-mail Mais Antigo ---")
        log_callback(f"Caixa/Marcador: {melhor_origem}")
        log_callback(f"De: {remetente}")
        log_callback(f"Assunto: {assunto}")
        log_callback(f"Data: {data_envio}")
        log_callback(f"ID: {melhor_msg.get('id')}")
        log_callback(f"--------------------------\n")

    except GoogleAPIError as erro:
        log_callback(f"Ocorreu um erro na API do Gmail: {erro}")
    except Exception as e:
        log_callback(f"Ocorreu um erro inesperado: {e}")

def fazer_backup_emails(
    pasta_destino, 
    client_secrets_file=None, 
    token_file=DEFAULT_TOKEN_FILE, 
    log_callback=print, 
    progress_callback=None, 
    check_cancel_callback=None, 
    data_inicio=None, 
    data_fim=None, 
    limite=None, 
    apagar_apos_download=False,
    marcador='TODAS',
    organizar_pastas=True,
    incluir_lixeira_spam=False,
    marcadores=None
):
    try:
        service = obter_servico_gmail(client_secrets_file, token_file, log_callback=log_callback)
        
        # Identifica dinamicamente todas as pastas da conta conectada
        log_callback("Identificando dinamicamente todas as pastas da conta conectada...")
        try:
            todas_labels = service.users().labels().list(userId='me').execute().get('labels', [])
            mapa_labels = {}
            pastas_descobertas = []
            for l in todas_labels:
                lid = l['id']
                lname = l['name']
                if lid in LABELS_IGNORAR:
                    continue
                nome_final = NOME_LABELS_SISTEMA.get(lid, lname)
                mapa_labels[lid] = nome_final
                pastas_descobertas.append(nome_final)
                
            log_callback(f"Pastas identificadas nesta conta ({len(pastas_descobertas)}):")
            for nome_p in sorted(pastas_descobertas, key=lambda s: s.lower()):
                log_callback(f"  📁 {nome_p}")
        except Exception as e:
            log_callback(f"Aviso ao consultar pastas da conta: {e}")
            mapa_labels = {}

        if marcadores is not None:
            if isinstance(marcadores, str):
                lista_marcadores = [marcadores]
            else:
                lista_marcadores = list(marcadores)
        elif isinstance(marcador, (list, tuple, set)):
            lista_marcadores = list(marcador)
        elif marcador and marcador != 'TODAS':
            lista_marcadores = [marcador]
        else:
            lista_marcadores = ['TODAS']

        modo_todas = ('TODAS' in lista_marcadores)

        if modo_todas:
            try:
                perfil = service.users().getProfile(userId='me').execute()
                total_estimado = perfil.get('messagesTotal', 0)
                log_callback(f"\nAlvo do backup: TODAS as pastas desta conta (~{total_estimado:,} e-mails)")
            except Exception:
                log_callback("\nAlvo do backup: TODAS as pastas desta conta")
        else:
            nomes_alvo = []
            total_estimado = 0
            for lid in lista_marcadores:
                nome = NOME_LABELS_SISTEMA.get(lid, mapa_labels.get(lid, lid))
                nomes_alvo.append(nome)
                try:
                    detalhe_lbl = service.users().labels().get(userId='me', id=lid).execute()
                    total_estimado += detalhe_lbl.get('messagesTotal', 0)
                except Exception:
                    pass
            desc_alvo = ", ".join(nomes_alvo)
            log_callback(f"\nAlvo do backup: {len(lista_marcadores)} pasta(s) selecionada(s) [{desc_alvo}] (~{total_estimado:,} e-mails estimados)")

        # Cria a pasta de destino se não existir
        os.makedirs(pasta_destino, exist_ok=True)
        
        query = ""
        if data_inicio:
            query += f" after:{data_inicio}"
        if data_fim:
            query += f" before:{data_fim}"
        query = query.strip()
        
        log_callback("Buscando mensagens... (isso pode demorar dependendo da quantidade de e-mails)")
        mensagens = []
        ids_vistos = set()

        if modo_todas:
            page_token = None
            while True:
                if check_cancel_callback and check_cancel_callback():
                    log_callback("Busca de mensagens cancelada pelo usuário.")
                    return
                    
                kwargs = {'userId': 'me', 'pageToken': page_token}
                if incluir_lixeira_spam:
                    kwargs['includeSpamTrash'] = True
                if query:
                    kwargs['q'] = query
                    
                resultado = service.users().messages().list(**kwargs).execute()
                novas = resultado.get('messages', [])
                for m in novas:
                    mid = m['id']
                    if mid not in ids_vistos:
                        ids_vistos.add(mid)
                        mensagens.append(m)
                        if limite and len(mensagens) >= limite:
                            break
                            
                if limite and len(mensagens) >= limite:
                    break
                    
                page_token = resultado.get('nextPageToken')
                if not page_token:
                    break
        else:
            for lid in lista_marcadores:
                if check_cancel_callback and check_cancel_callback():
                    log_callback("Busca de mensagens cancelada pelo usuário.")
                    return
                if limite and len(mensagens) >= limite:
                    break
                    
                nome_lbl = NOME_LABELS_SISTEMA.get(lid, mapa_labels.get(lid, lid))
                log_callback(f"Buscando e-mails da caixa/marcador '{nome_lbl}'...")
                page_token = None
                count_esta_pasta = 0
                
                while True:
                    if check_cancel_callback and check_cancel_callback():
                        log_callback("Busca de mensagens cancelada pelo usuário.")
                        return
                        
                    kwargs = {'userId': 'me', 'pageToken': page_token, 'labelIds': [lid]}
                    if lid in ['TRASH', 'SPAM']:
                        kwargs['includeSpamTrash'] = True
                    if query:
                        kwargs['q'] = query
                        
                    resultado = service.users().messages().list(**kwargs).execute()
                    novas = resultado.get('messages', [])
                    
                    for m in novas:
                        mid = m['id']
                        if mid not in ids_vistos:
                            ids_vistos.add(mid)
                            mensagens.append(m)
                            count_esta_pasta += 1
                            if limite and len(mensagens) >= limite:
                                break
                                
                    if limite and len(mensagens) >= limite:
                        break
                        
                    page_token = resultado.get('nextPageToken')
                    if not page_token:
                        break
                        
                log_callback(f"  -> Encontrados {count_esta_pasta} e-mails em '{nome_lbl}'.")

        if not mensagens:
            log_callback("Nenhum e-mail encontrado com os critérios informados.")
            return

        total_baixar = len(mensagens)
        log_callback(f"Iniciando o download de {total_baixar} e-mails...")
        
        for i, msg_info in enumerate(mensagens, start=1):
            if check_cancel_callback and check_cancel_callback():
                log_callback("Download cancelado pelo usuário.")
                return
                
            msg_id = msg_info['id']
            
            # Baixa o e-mail no formato 'raw' (necessário para gerar o .eml perfeitamente)
            mensagem = service.users().messages().get(userId='me', id=msg_id, format='raw').execute()
            msg_bytes = base64.urlsafe_b64decode(mensagem['raw'].encode('ASCII'))
            
            # Extrai e sanitiza o assunto para nomear o arquivo
            assunto_original = extrair_assunto_email(msg_bytes)
            assunto_sanitizado = sanitizar_nome_arquivo(assunto_original)
            nome_arquivo = f"{assunto_sanitizado} - {msg_id}.eml"
            
            if organizar_pastas:
                msg_labels = mensagem.get('labelIds', [])
                pastas_alvo = []
                for lid in msg_labels:
                    if lid in LABELS_IGNORAR:
                        continue
                    if not modo_todas and lid not in lista_marcadores:
                        continue
                    if lid in NOME_LABELS_SISTEMA:
                        pastas_alvo.append(NOME_LABELS_SISTEMA[lid])
                    elif lid in mapa_labels:
                        pastas_alvo.append(sanitizar_nome_pasta(mapa_labels[lid]))
                        
                if not pastas_alvo:
                    if not modo_todas:
                        for lid in lista_marcadores:
                            if lid in msg_labels:
                                nome_padrao = NOME_LABELS_SISTEMA.get(lid, mapa_labels.get(lid, lid))
                                pastas_alvo.append(sanitizar_nome_pasta(nome_padrao))
                        if not pastas_alvo and len(lista_marcadores) == 1:
                            lid = lista_marcadores[0]
                            nome_padrao = NOME_LABELS_SISTEMA.get(lid, mapa_labels.get(lid, lid))
                            pastas_alvo.append(sanitizar_nome_pasta(nome_padrao))
                    if not pastas_alvo:
                        pastas_alvo.append('Outros')
                        
                # Mantém pastas únicas preservando a ordem
                pastas_alvo = list(dict.fromkeys(pastas_alvo))
                
                for pasta_rel in pastas_alvo:
                    pasta_completa = os.path.join(pasta_destino, pasta_rel)
                    os.makedirs(pasta_completa, exist_ok=True)
                    caminho_arquivo = os.path.join(pasta_completa, nome_arquivo)
                    with open(caminho_arquivo, 'wb') as f:
                        f.write(msg_bytes)
                        
                desc_destino = ", ".join(pastas_alvo)
            else:
                caminho_arquivo = os.path.join(pasta_destino, nome_arquivo)
                with open(caminho_arquivo, 'wb') as f:
                    f.write(msg_bytes)
                desc_destino = "Pasta raiz"
                
            if apagar_apos_download:
                try:
                    service.users().messages().trash(userId='me', id=msg_id).execute()
                except Exception as e:
                    log_callback(f"Erro ao apagar o e-mail {msg_id}: {e}")
                    
            progresso = (i / total_baixar) * 100
            log_callback(f"[{i}/{total_baixar}] '{assunto_original}' salvo em [{desc_destino}] ({progresso:.2f}%)")
            if progress_callback:
                progress_callback(i, total_baixar)
                
        log_callback(f"\nBackup concluído com sucesso! Arquivos salvos em: {pasta_destino}")
        
    except GoogleAPIError as erro:
        log_callback(f"Ocorreu um erro na API do Gmail: {erro}")
    except Exception as e:
        log_callback(f"Ocorreu um erro inesperado: {e}")

if __name__ == '__main__':
    PASTA_BACKUP = "./backup_emails" 
    fazer_backup_emails(PASTA_BACKUP, marcador='TODAS', organizar_pastas=True)
