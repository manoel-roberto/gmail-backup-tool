# Gmail Backup Tool

Aplicativo desktop com interface gráfica moderna construído em Python e PyQt5 para realizar backup completo e seletivo de e-mails do Gmail no formato padronizado `.eml`.

## 🚀 Funcionalidades

- **Autenticação Simplificada:** Conexão direta com a API do Gmail via OAuth 2.0 no navegador.
- **Seleção Múltipla de Caixas/Marcadores:**
  - Backup de todas as pastas da conta (incluindo arquivados).
  - Atalho rápido para selecionar apenas `Inbox + Enviados`.
  - Seleção livre e personalizada de pastas de sistema ou marcadores criados pelo usuário.
- **Organização Inteligente:** Cria automaticamente subpastas no destino correspondentes aos marcadores selecionados.
- **Deduplicação de Downloads:** E-mails presentes em mais de um marcador selecionado são baixados uma única vez.
- **Filtros Avançados:** Filtro por período de datas (Início e Fim) e limite máximo de e-mails.
- **Opção de Expurgo:** Possibilidade de mover para a lixeira após o download concluído.
- **Consultas Rápidas:** Localização imediata do 1º e-mail (mais recente) e do mais antigo.

---

## 🛠️ Executando Localmente

### Pré-requisitos
- Python 3.10 ou superior

### Instalação
```bash
# Clone o repositório
git clone <url-do-repositorio>
cd email

# Crie e ative o ambiente virtual
python -m venv .venv
source .venv/bin/activate  # No Windows: .venv\Scripts\activate

# Instale as dependências
pip install -r requirements.txt

# Execute a aplicação
python app.py
```

---

## ⚙️ Automação de Compilação (GitHub Actions)

O repositório conta com uma pipeline automatizada no GitHub Actions configurada em `.github/workflows/build.yml`:

- **Compilação Cruzada:** Gera automaticamente binários para:
  - 🪟 **Windows:** `GmailBackup-Windows.exe` (executável único sem terminal).
  - 🐧 **Linux:** `GmailBackup-Linux` (executável binário ELF standalone).
- **Gatilhos:**
  - `push` na branch `main`.
  - Disparo manual através da aba **Actions** (`workflow_dispatch`).
  - Criação de tags de versão (ex: `v1.0.0`), que publica uma Release automática com os arquivos anexados.
- **Download dos Executáveis:** Os executáveis gerados em cada compilação ficam disponíveis para download direto na seção **Artifacts** de cada execução do GitHub Actions.
