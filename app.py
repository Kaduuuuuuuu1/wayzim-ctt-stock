import os
import sys
import sqlite3
from datetime import datetime
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image
import base64

# Força o Python a assumir exatamente a pasta onde este ficheiro (app.py) está guardado
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

try:
    import zxingcpp
    LEITOR_DISPONIVEL = True
except ImportError:
    LEITOR_DISPONIVEL = False

st.set_page_config(page_title="Wayzim & CTT - Gestão", page_icon="📦", layout="wide", initial_sidebar_state="collapsed")

# --- BASE DE DADOS E CONFIGURAÇÃO ---
DB = os.path.join(BASE_DIR, "armazem.db")
IMAGENS_DIR = os.path.join(BASE_DIR, "imagens_pecas")
LIMITE_STOCK_BAIXO = 2

os.makedirs(IMAGENS_DIR, exist_ok=True)

def ligar_base_dados():
    return sqlite3.connect(DB)

def preparar_base_dados():
    with ligar_base_dados() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS pecas (
                id INTEGER PRIMARY KEY,
                codigo TEXT UNIQUE NOT NULL,
                codigo_limpo TEXT UNIQUE,
                nome TEXT NOT NULL,
                localizacao TEXT,
                stock INTEGER NOT NULL DEFAULT 0,
                imagem TEXT,
                armazem TEXT DEFAULT 'Algoz'
            )
        """)
        
        cursor = con.execute("PRAGMA table_info(pecas)")
        colunas = [col[1] for col in cursor.fetchall()]
        if "imagem" not in colunas:
            con.execute("ALTER TABLE pecas ADD COLUMN imagem TEXT")
        if "armazem" not in colunas:
            con.execute("ALTER TABLE pecas ADD COLUMN armazem TEXT DEFAULT 'Algoz'")

        con.execute("""
            CREATE TABLE IF NOT EXISTS movimentos (
                id INTEGER PRIMARY KEY,
                peca_id INTEGER,
                tipo TEXT NOT NULL,
                quantidade INTEGER DEFAULT 0,
                maquina TEXT,
                observacoes TEXT,
                tecnico TEXT,
                data TEXT NOT NULL
            )
        """)
        
        # Migração caso a tabela movimentos já exista
        cursor_mov = con.execute("PRAGMA table_info(movimentos)")
        colunas_mov = [col[1] for col in cursor_mov.fetchall()]
        if "observacoes" not in colunas_mov:
            con.execute("ALTER TABLE movimentos ADD COLUMN observacoes TEXT")
        
        con.execute("""
            CREATE TABLE IF NOT EXISTS tecnicos (
                id INTEGER PRIMARY KEY,
                nome TEXT UNIQUE NOT NULL,
                telemovel TEXT NOT NULL
            )
        """)
        
        tecnicos_iniciais = [
            ("Carlos Souza", "967080103"),
            ("Nuno Ricardo", "922229163"),
            ("Rui Miguel", "922229169"),
            ("Eduardo Silva", "969510705"),
            ("Jorge Nunes", "927354397"),
            ("Thomas Halaiwa", "969510753"),
            ("Sergio Carvalho", "924750391"),
            ("Antonio Marcos", "967080208"),
            ("Fernando", "924750381"),
            ("Gil Monteiro", "926394020"),
            ("Camilo", "926701803"),
            ("Pedro Nabaz", "961703115"),
            ("Maria João", "964572917")
        ]
        
        for t_nome, t_tel in tecnicos_iniciais:
            con.execute("""
                INSERT INTO tecnicos (nome, telemovel) VALUES (?, ?)
                ON CONFLICT(nome) DO UPDATE SET telemovel = excluded.telemovel
            """, (t_nome, t_tel))

def inserir_pecas_iniciais():
    pecas_excel = [
        ("C20", "Rolamentos UCF 208", 10, "A01", "Algoz"),
        ("C42", "Tela 6230YL-35E/23R", 10, "B02", "Algoz"),
        ("C46", "Tela Cart 2445x163", 22, "B02", "Algoz"),
        ("C47", "Tela Singulator 1202x180", 4, "B02", "Algoz"),
    ]
    with ligar_base_dados() as con:
        for cod, nome, qtd, loc, arm in pecas_excel:
            c_form = cod.upper().strip()
            c_limp = c_form.replace("-", "").replace(" ", "").replace("O", "0")
            con.execute("""
                INSERT INTO pecas (codigo, codigo_limpo, nome, localizacao, stock, armazem) 
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(codigo) DO UPDATE SET nome = excluded.nome
            """, (c_form, c_limp, nome, loc, qtd, arm))

preparar_base_dados()
inserir_pecas_iniciais()

def obter_imagem_base64(caminho_ficheiro):
    if os.path.exists(caminho_ficheiro):
        with open(caminho_ficheiro, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None

# --- AUTENTICAÇÃO E TELA DE LOGIN ---
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
    st.session_state.utilizador_atual = ""

if not st.session_state.autenticado:
    img_fundo_path = None
    
    for ext in ["jpg", "jpeg", "png"]:
        if os.path.exists(os.path.join(BASE_DIR, f"fundo.{ext}")):
            img_fundo_path = os.path.join(BASE_DIR, f"fundo.{ext}")
            break

    css_fundo = ""
    if img_fundo_path:
        b64_fundo = obter_imagem_base64(img_fundo_path)
        css_fundo = f"""
            [data-testid="stAppViewContainer"] {{
                background: linear-gradient(rgba(10, 15, 30, 0.65), rgba(10, 15, 30, 0.85)), 
                            url("data:image/jpeg;base64,{b64_fundo}");
                background-size: cover;
                background-position: center;
                background-repeat: no-repeat;
            }}
        """
    else:
        css_fundo = "[data-testid='stAppViewContainer'] { background-color: #0B0F19; }"

    st.markdown(f"""
        <style>
        {css_fundo}
        
        header {{visibility: hidden;}}
        footer {{visibility: hidden;}}
        
        [data-testid="stForm"] {{
            background: rgba(15, 23, 42, 0.90) !important;
            padding: 2.5rem 3.5rem !important;
            border-radius: 16px !important;
            border: 1px solid rgba(56, 189, 248, 0.4) !important;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.8), 0 0 20px rgba(56, 189, 248, 0.15) !important;
            backdrop-filter: blur(10px);
            margin-top: 1rem;
        }}

        .ticker-wrap {{
            width: 100%;
            overflow: hidden;
            background: rgba(2, 132, 199, 0.2);
            border-radius: 8px;
            padding: 8px 0;
            margin-bottom: 24px;
            border: 1px solid rgba(56, 189, 248, 0.3);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }}
        .ticker {{
            display: inline-block;
            white-space: nowrap;
            padding-left: 100%;
            animation: scroll-ticker 25s linear infinite;
        }}
        .ticker:hover {{
            animation-play-state: paused;
        }}
        .ticker-item {{
            display: inline-block;
            padding: 0 2.5rem;
            font-size: 0.9rem;
            color: #E2E8F0;
            font-weight: 500;
            letter-spacing: 0.5px;
        }}
        .ticker-item span {{
            color: #38BDF8;
            font-weight: bold;
        }}
        @keyframes scroll-ticker {{
            0% {{ transform: translate3d(0, 0, 0); }}
            100% {{ transform: translate3d(-100%, 0, 0); }}
        }}

        [data-testid="stFormSubmitButton"] button {{ 
            background: linear-gradient(135deg, #0284C7 0%, #0369A1 100%); 
            color: white !important; 
            border-radius: 8px; 
            padding: 0.6rem 1rem; 
            font-size: 1.1rem; 
            border: 1px solid #38BDF8; 
            font-weight: bold; 
            width: 100%; 
            margin-top: 1rem;
            transition: 0.3s ease; 
            box-shadow: 0 4px 15px rgba(2, 132, 199, 0.5); 
        }}
        [data-testid="stFormSubmitButton"] button:hover {{ 
            background: linear-gradient(135deg, #0369A1 0%, #075985 100%); 
            transform: translateY(-2px); 
            box-shadow: 0 6px 20px rgba(2, 132, 199, 0.7); 
        }}
        
        .stTextInput>div>div>input, .stSelectbox>div>div>div {{ 
            background-color: rgba(0, 0, 0, 0.6) !important; 
            color: #FFFFFF !important; 
            border: 1px solid rgba(56, 189, 248, 0.6) !important; 
            border-radius: 8px !important; 
            font-size: 1rem !important; 
        }}
        
        .assinatura-card {{ 
            text-align: center; 
            margin-top: 2.5rem; 
            padding-top: 1rem;
            border-top: 1px solid rgba(255, 255, 255, 0.15);
            font-size: 0.95rem; 
            color: #CBD5E1; 
        }}
        .assinatura-card span {{ 
            display: block;
            margin-top: 0.3rem;
            color: #38BDF8; 
            font-weight: 900; 
            font-size: 1.2rem;
            text-transform: uppercase;
            letter-spacing: 2px;
            text-shadow: 0 0 10px rgba(56, 189, 248, 0.7);
        }}
        </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
            <div class='ticker-wrap'>
                <div class='ticker'>
                    <span class='ticker-item'>⚠️ <span>Aviso:</span> Manutenção preventiva agendada para os equipamentos principais.</span>
                    <span class='ticker-item'>🔧 <span>Lembrete:</span> Verificar sempre o stock de telas do Singulator e dos Carts.</span>
                    <span class='ticker-item'>📦 <span>Sistema:</span> Gestão e registo de peças em tempo real.</span>
                    <span class='ticker-item'>⚡ <span>Operação:</span> Garantir disponibilidade máxima da linha Wayzim & CTT.</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

        with st.form("login_form"):
            st.markdown("<h2 style='text-align: center; color: #FFF; font-weight: 800; font-size: 2.2rem; margin-bottom: 0.2rem;'>📦 Wayzim & CTT</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; font-size: 1rem; color: #38BDF8; margin-bottom: 2rem;'>Sistema Profissional de Gestão de Armazém</p>", unsafe_allow_html=True)
            
            with ligar_base_dados() as con:
                lista_tecnicos_db = [row[0] for row in con.execute("SELECT nome FROM tecnicos ORDER BY nome").fetchall()]
            
            input_nome = st.selectbox("Técnico Operacional", lista_tecnicos_db)
            input_telemovel = st.text_input("Palavra-passe (Telemóvel)", type="password")

            btn_login = st.form_submit_button("Entrar no Sistema")

            st.markdown("<div class='assinatura-card'>Desenvolvido com excelência por <span>Carlos Souza</span></div>", unsafe_allow_html=True)

        if btn_login:
            with ligar_base_dados() as con:
                res = con.execute("SELECT telemovel FROM tecnicos WHERE nome = ?", (input_nome,)).fetchone()
            if res and res[0].strip() == input_telemovel.strip():
                st.session_state.autenticado = True
                st.session_state.utilizador_atual = input_nome
                st.rerun()
            else:
                st.error("Credenciais incorretas. Verifica o número de telemóvel.")
                
    st.stop()

# --- SISTEMA APÓS LOGIN (ESTILOS E FUNCIONALIDADES) ---
st.markdown("""
    <style>
    .stApp { background-color: #0B0F19; color: #F8FAFC; }
    h1, h2, h3, h4, h5, h6, span, label { color: #F8FAFC !important; }
    p { color: #94A3B8 !important; }
    .stButton>button { background-color: #2563EB; color: white; border-radius: 6px; padding: 0.4rem 1rem; font-size: 0.85rem; border: none; font-weight: 600; width: 100%; transition: 0.2s; }
    .stButton>button:hover { background-color: #1D4ED8; }
    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox>div>div>div { background-color: #111827; color: #F8FAFC; border: 1px solid #1F2937; border-radius: 6px; font-size: 0.85rem; }
    .footer-app { text-align: center; margin-top: 4rem; padding: 1rem; font-size: 0.75rem; color: #475569; border-top: 1px solid #1F2937; }
    .footer-app span { color: #38BDF8; font-weight: 600; text-transform: uppercase; }
    </style>
""", unsafe_allow_html=True)

def normalizar_codigo(texto):
    if not texto: return ""
    return str(texto).upper().strip().replace("-", "").replace(" ", "").replace("O", "0")

def registar_movimento(peca_id, tipo, quantidade, maquina, observacoes, tecnico):
    with ligar_base_dados() as con:
        if peca_id:
            stock_atual = con.execute("SELECT stock FROM pecas WHERE id = ?", (peca_id,)).fetchone()[0]
            if tipo == "Saída" and quantidade > stock_atual:
                return False, f"Stock insuficiente ({stock_atual} disp.)."
            novo_stock = stock_atual - quantidade if tipo == "Saída" else stock_atual + quantidade
            con.execute("UPDATE pecas SET stock = ? WHERE id = ?", (novo_stock, peca_id))
        
        con.execute("INSERT INTO movimentos (peca_id, tipo, quantidade, maquina, observacoes, tecnico, data) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (peca_id, tipo, quantidade, maquina, observacoes, tecnico, datetime.now().isoformat()))
    return True, "Registo efetuado com sucesso."

if "pagina_atual" not in st.session_state:
    st.session_state.pagina_atual = "📦 Stock"

col_top1, col_top2 = st.columns([3, 1])
with col_top1:
    st.markdown(f"<h3 style='margin: 0; font-size: 1.3rem;'>Wayzim & CTT Express — Gestão de Armazém</h3><p style='margin: 0; font-size: 0.8rem; color: #38BDF8;'>Operador ativo: <b>{st.session_state.utilizador_atual}</b></p>", unsafe_allow_html=True)
with col_top2:
    if st.button("Sair da Sessão"):
        st.session_state.autenticado = False
        st.rerun()

st.divider()

eh_admin = (st.session_state.utilizador_atual == "Carlos Souza")
opcoes_menu = ["📦 Stock", "➕ Nova Peça", "🔄 Movimentos", "📝 Registar Preventiva", "📷 Leitor QR", "📋 Histórico"]
if eh_admin: opcoes_menu.append("⚙️ Admin")

cols_nav = st.columns(len(opcoes_menu))
for i, opcao in enumerate(opcoes_menu):
    with cols_nav[i]:
        if st.button(opcao, key=f"nav_{opcao}", use_container_width=True):
            st.session_state.pagina_atual = opcao
            st.rerun()

st.markdown("<br>", unsafe_allow_html=True)

if st.session_state.pagina_atual == "📦 Stock":
    col_f1, col_f2 = st.columns([3, 1])
    with col_f1:
        termo = st.text_input("🔍 Pesquisar peça...", placeholder="Escreve o código ou o nome da peça...", label_visibility="collapsed")
    with col_f2:
        apenas_critico = st.checkbox("⚠️ Stock Baixo (≤2)")

    with ligar_base_dados() as con:
        df = pd.read_sql_query("SELECT id, codigo, nome, armazem, localizacao, stock, imagem FROM pecas ORDER BY codigo", con)

    if df.empty:
        st.info("Sem peças registadas na base de dados.")
    else:
        if termo:
            df = df[df["codigo"].str.contains(termo, case=False, na=False) | df["nome"].str.contains(termo, case=False, na=False)]
        
        if apenas_critico:
            df = df[df["stock"] <= LIMITE_STOCK_BAIXO]

        tab_alg, tab_rio = st.tabs(["Algoz", "Rio de Mouro"])
        
        def render_lista(sub_df):
            if sub_df.empty:
                st.markdown("<p style='font-size: 0.85rem; color: #64748B;'>Nenhuma peça encontrada neste armazém.</p>", unsafe_allow_html=True)
                return
            for _, r in sub_df.iterrows():
                c1, c2, c3, c4, c5 = st.columns([1.5, 2.5, 0.9, 0.8, 1.2])
                with c1:
                    img_val = r["imagem"]
                    if pd.notna(img_val) and str(img_val).strip() and str(img_val).lower() != 'nan' and os.path.exists(os.path.join(IMAGENS_DIR, str(img_val))):
                        st.image(os.path.join(IMAGENS_DIR, str(img_val)), width=130)
                    else:
                        st.markdown("<span style='font-size: 0.8rem; color: #475569;'>Sem fotografia</span>", unsafe_allow_html=True)
                with c2:
                    st.markdown(f"<span style='font-size: 0.95rem;'><b>{r['codigo']}</b> — {r['nome']}</span><br><span style='font-size: 0.85rem; color: #64748B;'>Localização: {r['localizacao'] or '—'}</span>", unsafe_allow_html=True)
                with c3:
                    cor = "#EF4444" if r["stock"] <= LIMITE_STOCK_BAIXO else "#22C55E"
                    st.markdown(f"<span style='font-size: 1.05rem; font-weight: bold; color: {cor};'>Qtd: {r['stock']}</span>", unsafe_allow_html=True)
                with c4:
                    with st.popover("📷 Foto"):
                        up_f = st.file_uploader(f"Atualizar foto ({r['codigo']})", type=["png", "jpg", "jpeg"], key=f"f_{r['id']}")
                        if up_f and st.button("Guardar Foto", key=f"b_{r['id']}"):
                            ext = up_f.name.split(".")[-1]
                            novo_nome = f"{normalizar_codigo(r['codigo'])}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}"
                            with open(os.path.join(IMAGENS_DIR, novo_nome), "wb") as f: f.write(up_f.getbuffer())
                            with ligar_base_dados() as con:
                                con.execute("UPDATE pecas SET imagem = ? WHERE id = ?", (novo_nome, r["id"]))
                            st.rerun()
                with c5:
                    if st.button("Movimento ➔", key=f"mov_{r['id']}"):
                        st.session_state["peca_selecionada_mov"] = r['id']
                        st.session_state.pagina_atual = "🔄 Movimentos"
                        st.rerun()

        with tab_alg: render_lista(df[df["armazem"] == "Algoz"])
        with tab_rio: render_lista(df[df["armazem"] == "Rio de Mouro"])

elif st.session_state.pagina_atual == "➕ Nova Peça":
    st.markdown("<p style='font-size: 1.1rem; font-weight: bold;'>Adicionar Nova Peça ao Sistema</p>", unsafe_allow_html=True)
    arm = st.radio("Armazém de Destino", ["Algoz", "Rio de Mouro"], horizontal=True)
    col_n1, col_n2 = st.columns(2)
    with col_n1:
        cod = st.text_input("Código da Peça")
        loc = st.text_input("Localização")
    with col_n2:
        nom = st.text_input("Nome Descritivo")
        qtd = st.number_input("Quantidade Inicial", min_value=0, step=1)
    foto = st.file_uploader("Fotografia da Peça", type=["png", "jpg", "jpeg"])

    if st.button("Registar Nova Peça"):
        if not cod or not nom:
            st.error("Preenche o código e o nome.")
        else:
            c_form, c_limp = cod.upper().strip(), normalizar_codigo(cod)
            img_nome = None
            if foto:
                ext = foto.name.split(".")[-1]
                img_nome = f"{c_limp}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}"
                with open(os.path.join(IMAGENS_DIR, img_nome), "wb") as f: f.write(foto.getbuffer())
            try:
                with ligar_base_dados() as con:
                    con.execute("INSERT INTO pecas (codigo, codigo_limpo, nome, localizacao, stock, imagem, armazem) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                (c_form, c_limp, nom, loc, qtd, img_nome, arm))
                st.success("Registada com sucesso!")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("Código já existe.")

elif st.session_state.pagina_atual == "🔄 Movimentos":
    st.markdown("<p style='font-size: 1.1rem; font-weight: bold;'>Registo de Saídas / Entradas de Stock</p>", unsafe_allow_html=True)
    with ligar_base_dados() as con:
        opcoes = con.execute("SELECT id, codigo, nome, stock, imagem, armazem FROM pecas ORDER BY armazem, codigo").fetchall()
    
    if not opcoes:
        st.info("Não existem peças disponíveis.")
    else:
        indice_default = 0
        if "peca_selecionada_mov" in st.session_state:
            for idx, p in enumerate(opcoes):
                if p[0] == st.session_state["peca_selecionada_mov"]:
                    indice_default = idx
                    break
            del st.session_state["peca_selecionada_mov"]

        sel = st.selectbox("Selecionar Peça", opcoes, index=indice_default, format_func=lambda p: f"[{p[5]}] {p[1]} — {p[2]} (Stock Atual: {p[3]})")
        
        tp = st.radio("Tipo de Movimento", ["Saída", "Entrada"], horizontal=True)
        qt = st.number_input("Quantidade", min_value=1, step=1)
        
        col_mq1, col_mq2 = st.columns(2)
        with col_mq1:
            tipo_equipamento = st.selectbox("Sistema / Equipamento", ["Singulator", "Sorter", "Carts", "Tapetes Singulator", "Telas Carts", "Tulhas", "Outro"])
        with col_mq2:
            detalhe_equip = st.text_input("Detalhe / Número de Referência", placeholder="Ex: Cart 143 / Chute 57")
        
        mq_final = f"{tipo_equipamento} — {detalhe_equip}" if detalhe_equip else tipo_equipamento
        obs_movimento = st.text_area("📝 Apontamentos / Notas", placeholder="Observações sobre a aplicação da peça...")
        
        if st.button("Confirmar e Registar Movimento"):
            suc, msg = registar_movimento(sel[0], tp, qt, mq_final, obs_movimento, st.session_state.utilizador_atual)
            if suc: st.success(msg); st.rerun()
            else: st.error(msg)

elif st.session_state.pagina_atual == "📝 Registar Preventiva":
    st.markdown("<p style='font-size: 1.1rem; font-weight: bold;'>Registar Conclusão de Preventiva / Apontamentos (Sem baixar stock)</p>", unsafe_allow_html=True)
    st.markdown("<p style='font-size: 0.85rem; color: #94A3B8;'>Usa este ecrã quando finalizaste a intervenção na máquina mas não gastaste nenhuma peça do armazém.</p>", unsafe_allow_html=True)
    
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        sistema_prev = st.selectbox("Sistema / Equipamento Intervencionado", ["Singulator", "Sorter", "Carts", "Tapetes Singulator", "Telas Carts", "Tulhas", "Linha Geral", "Outro"], key="prev_sis")
    with col_p2:
        detalhe_prev = st.text_input("Detalhe / Número (Opcional)", placeholder="Ex: Cart 202 / Linha 3", key="prev_det")
    
    maquina_prev_final = f"{sistema_prev} — {detalhe_prev}" if detalhe_prev else sistema_prev
    obs_prev = st.text_area("📝 Relatório de Preventiva / Pendências", placeholder="Ex: Preventiva executada sem anomalias. Ficou pendente verificar sensor X na próxima intervenção...", key="prev_obs")

    if st.button("Guardar Relatório de Preventiva"):
        if not obs_prev:
            st.warning("Por favor, escreve pelo menos uma breve nota no relatório.")
        else:
            suc, msg = registar_movimento(None, "Preventiva", 0, maquina_prev_final, obs_prev, st.session_state.utilizador_atual)
            if suc:
                st.success("Relatório de preventiva registado com sucesso para toda a equipa consultar!")
            else:
                st.error(msg)

elif st.session_state.pagina_atual == "📷 Leitor QR":
    st.markdown("<p style='font-size: 1.1rem; font-weight: bold;'>Leitor de Códigos QR e de Barras</p>", unsafe_allow_html=True)
    st.caption("💡 Dica: Se a câmara não abrir após dar permissão, clica em 'Stock' e volta a abrir o 'Leitor QR'.")
    if not LEITOR_DISPONIVEL:
        st.error("Módulo de leitura indisponível.")
    else:
        cam = st.camera_input("Capturar fotografia da etiqueta")
        if cam:
            res = zxingcpp.read_barcodes(np.array(Image.open(cam).convert("RGB")))
            if not res:
                st.warning("Nenhum código detetado na imagem.")
            else:
                c_lido = res[0].text.strip()
                with ligar_base_dados() as con:
                    peca = con.execute("SELECT id, codigo, nome, stock, armazem, imagem FROM pecas WHERE codigo = ? OR codigo_limpo = ?", 
                                       (c_lido.upper(), normalizar_codigo(c_lido))).fetchone()
                if not peca:
                    st.error(f"O código '{c_lido}' não foi encontrado.")
                else:
                    peca_id, codigo, nome, stock, armazem, img_peca = peca
                    st.success(f"Peça identificada: {nome} (Armazém: {armazem})")
                    
                    q_ret = st.number_input("Quantidade a retirar", min_value=1, step=1, key="q_ret_leitor")
                    
                    col_l1, col_l2 = st.columns(2)
                    with col_l1:
                        eq_leitor = st.selectbox("Equipamento", ["Singulator", "Sorter", "Carts", "Tapetes Singulator", "Telas Carts", "Tulhas", "Outro"], key="eq_leitor")
                    with col_l2:
                        det_leitor = st.text_input("Detalhe", placeholder="Ex: Cart 202", key="det_leitor")
                    
                    m_ret = f"{eq_leitor} — {det_leitor}" if det_leitor else eq_leitor
                    obs_leitor = st.text_area("📝 Apontamentos", key="obs_leitor")
                    
                    if st.button("Registar Saída Imediata"):
                        suc, msg = registar_movimento(peca_id, "Saída", q_ret, m_ret, obs_leitor, st.session_state.utilizador_atual)
                        if suc: st.success(msg); st.rerun()
                        else: st.error(msg)
            
elif st.session_state.pagina_atual == "📋 Histórico":
    st.markdown("<p style='font-size: 1.1rem; font-weight: bold;'>Histórico Global de Movimentos e Preventivas</p>", unsafe_allow_html=True)
    with ligar_base_dados() as con:
        df_h = pd.read_sql_query("""
            SELECT 
                strftime('%d/%m %H:%M', m.data) AS Data, 
                COALESCE(p.codigo, '—') AS Código, 
                COALESCE(p.nome, 'Registo de Preventiva / Inspeção') AS Peça, 
                m.tipo AS Tipo, 
                CASE WHEN m.quantidade > 0 THEN m.quantidade ELSE '—' END AS Qtd, 
                m.tecnico AS Técnico, 
                m.maquina AS Equipamento, 
                m.observacoes AS Apontamentos 
            FROM movimentos m 
            LEFT JOIN pecas p ON p.id = m.peca_id 
            ORDER BY m.id DESC
        """, con)
    
    if df_h.empty: 
        st.info("Ainda não existem registos.")
    else: 
        csv_data = df_h.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Exportar Histórico para CSV",
            data=csv_data,
            file_name=f"historico_preventivas_wayzim_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )
        st.dataframe(df_h, hide_index=True, use_container_width=True)

elif eh_admin and st.session_state.pagina_atual == "⚙️ Admin":
    st.markdown("<p style='font-size: 1.1rem; font-weight: bold;'>Painel de Administração — Técnicos</p>", unsafe_allow_html=True)
    
    with st.form("form_novo_tecnico"):
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            t_nome_novo = st.text_input("Nome Completo do Técnico")
        with col_t2:
            t_tel_novo = st.text_input("Telemóvel (Password)")
        
        btn_guardar_t = st.form_submit_button("Guardar Técnico")
        if btn_guardar_t:
            if not t_nome_novo or not t_tel_novo:
                st.error("Preenche o nome e o telemóvel.")
            else:
                with ligar_base_dados() as con:
                    con.execute("""
                        INSERT INTO tecnicos (nome, telemovel) VALUES (?, ?)
                        ON CONFLICT(nome) DO UPDATE SET telemovel = excluded.telemovel
                    """, (t_nome_novo.strip(), t_tel_novo.strip()))
                st.success(f"Técnico '{t_nome_novo}' registado!")
                st.rerun()

    st.divider()
    with ligar_base_dados() as con:
        lista_tec_adm = con.execute("SELECT id, nome, telemovel FROM tecnicos ORDER BY nome").fetchall()
    
    for t_id, t_nome, t_tel in lista_tec_adm:
        cols_tec = st.columns([2, 2, 1])
        with cols_tec[0]:
            st.markdown(f"<span style='font-size: 0.9rem;'><b>{t_nome}</b></span>", unsafe_allow_html=True)
        with cols_tec[1]:
            st.markdown(f"<span style='font-size: 0.9rem; color: #94A3B8;'>{t_tel}</span>", unsafe_allow_html=True)
        with cols_tec[2]:
            if t_nome != "Carlos Souza":
                if st.button("🗑️ Apagar", key=f"del_tec_{t_id}"):
                    with ligar_base_dados() as con:
                        con.execute("DELETE FROM tecnicos WHERE id = ?", (t_id,))
                    st.success(f"Técnico {t_nome} removido.")
                    st.rerun()
            else:
                st.markdown("<span style='font-size: 0.75rem; color: #64748B;'>Admin Principal</span>", unsafe_allow_html=True)

st.markdown("<div class='footer-app'>Wayzim & CTT Express Stock Manager — Desenvolvido por <span>Carlos Souza</span></div>", unsafe_allow_html=True)
