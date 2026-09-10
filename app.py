import os
import sys
import sqlite3
from datetime import datetime
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image
import base64
import requests
from io import BytesIO
from fpdf import FPDF

# Força o Python a assumir exatamente a pasta onde este ficheiro (app.py) está guardado
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

try:
    import zxingcpp
    LEITOR_DISPONIVEL = True
except ImportError:
    LEITOR_DISPONIVEL = False

st.set_page_config(page_title="OptiMaint - Wayzim & CTT", page_icon="⚡", layout="wide", initial_sidebar_state="collapsed")

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
                data TEXT NOT NULL,
                imagem TEXT
            )
        """)
        
        cursor_mov = con.execute("PRAGMA table_info(movimentos)")
        colunas_mov = [col[1] for col in cursor_mov.fetchall()]
        if "observacoes" not in colunas_mov:
            con.execute("ALTER TABLE movimentos ADD COLUMN observacoes TEXT")
        if "imagem" not in colunas_mov:
            con.execute("ALTER TABLE movimentos ADD COLUMN imagem TEXT")
        
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

# --- INTEGRAÇÃO NEXTBIT ---
def enviar_para_nextbit(dados_tecnicos):
    url_api_nextbit = "https://api.nextbit.exemplo/v1/manutencao"
    headers = {"Authorization": "Bearer TOKEN_SECRETO_NEXTBIT"}
    try:
        return True, "Integrado com Nextbit com sucesso."
    except Exception as e:
        return False, f"Erro na integração Nextbit: {str(e)}"

# --- GERADOR DE RELATÓRIO PDF ---
class PDFRelatorio(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'OptiMaint — Relatório Técnico Oficial (Wayzim & CTT)', 0, 1, 'C')
        self.set_font('Arial', '', 9)
        self.cell(0, 6, f'Emitido em: {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()} — Desenvolvido por Carlos Souza', 0, 0, 'C')

def gerar_pdf_relatorio(tipo_relatorio, dados_df):
    pdf = PDFRelatorio()
    pdf.add_page()
    pdf.set_font('Arial', 'B', 12)
    
    pdf.cell(0, 8, f'Assunto: Relatório de {tipo_relatorio}', 0, 1, 'L')
    pdf.ln(4)
    
    pdf.set_font('Arial', 'B', 9)
    pdf.set_fill_color(2, 132, 199)
    pdf.set_text_color(255, 255, 255)
    
    colunas = list(dados_df.columns)
    larguras = [30, 25, 45, 20, 25, 45] if len(colunas) >= 6 else [40, 40, 40, 40, 40]
    
    for i, col in enumerate(colunas[:6]):
        pdf.cell(larguras[i] if i < len(larguras) else 25, 7, str(col)[:15], 1, 0, 'C', True)
    pdf.ln()
    
    pdf.set_font('Arial', '', 8)
    pdf.set_text_color(0, 0, 0)
    for _, linha in dados_df.iterrows():
        for i, val in enumerate(list(linha.values)[:6]):
            pdf.cell(larguras[i] if i < len(larguras) else 25, 6, str(val)[:20], 1, 0, 'L')
        pdf.ln()
        
    pdf.ln(10)
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 6, 'Observações Finais e Visto da Chefia:', 0, 1, 'L')
    pdf.set_font('Arial', '', 9)
    pdf.multi_cell(0, 6, 'Relatório verificado e validado pela plataforma OptiMaint em operações Wayzim & CTT.')
    pdf.ln(10)
    pdf.cell(90, 6, '________________________________________', 0, 1, 'L')
    pdf.cell(90, 6, 'Assinatura do Técnico Responsável', 0, 0, 'L')
    
    return pdf.output(dest='S').encode('latin1')

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

    css_fundo = f"""
        [data-testid="stAppViewContainer"] {{
            background: linear-gradient(rgba(10, 15, 30, 0.65), rgba(10, 15, 30, 0.85)), 
                        url("data:image/jpeg;base64,{obter_imagem_base64(img_fundo_path)}");
            background-size: cover; background-position: center;
        }}
    """ if img_fundo_path else "[data-testid='stAppViewContainer'] { background-color: #0B0F19; }"

    st.markdown(f"""
        <style>
        {css_fundo}
        header {{visibility: hidden;}} footer {{visibility: hidden;}}
        [data-testid="stForm"] {{
            background: rgba(15, 23, 42, 0.90) !important;
            padding: 2.5rem 3.5rem !important; border-radius: 16px !important;
            border: 1px solid rgba(56, 189, 248, 0.4) !important;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.8);
        }}
        [data-testid="stFormSubmitButton"] button {{ 
            background: linear-gradient(135deg, #0284C7 0%, #0369A1 100%); 
            color: white !important; border-radius: 8px; width: 100%; font-weight: bold;
        }}
        </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.markdown("<h2 style='text-align: center; color: #FFF;'>⚡ OptiMaint</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: #38BDF8;'>Plataforma Profissional de Gestão & Manutenção</p>", unsafe_allow_html=True)
            
            with ligar_base_dados() as con:
                lista_tecnicos_db = [row[0] for row in con.execute("SELECT nome FROM tecnicos ORDER BY nome").fetchall()]
            
            input_nome = st.selectbox("Técnico Operacional", lista_tecnicos_db)
            input_telemovel = st.text_input("Palavra-passe (Telemóvel)", type="password")
            btn_login = st.form_submit_button("Entrar no Sistema")

        if btn_login:
            with ligar_base_dados() as con:
                res = con.execute("SELECT telemovel FROM tecnicos WHERE nome = ?", (input_nome,)).fetchone()
            if res and res[0].strip() == input_telemovel.strip():
                st.session_state.autenticado = True
                st.session_state.utilizador_atual = input_nome
                st.rerun()
            else:
                st.error("Credenciais incorretas.")
    st.stop()

# --- SISTEMA APÓS LOGIN ---
st.markdown("""
    <style>
    .stApp { background-color: #0B0F19; color: #F8FAFC; }
    h1, h2, h3, h4, h5, h6, span, label { color: #F8FAFC !important; }
    </style>
""", unsafe_allow_html=True)

def normalizar_codigo(texto):
    if not texto: return ""
    return str(texto).upper().strip().replace("-", "").replace(" ", "").replace("O", "0")

def registar_movimento(peca_id, tipo, quantidade, maquina, observacoes, tecnico, imagem=None):
    with ligar_base_dados() as con:
        if peca_id:
            stock_atual = con.execute("SELECT stock FROM pecas WHERE id = ?", (peca_id,)).fetchone()[0]
            if tipo == "Saída" and quantidade > stock_atual:
                return False, f"Stock insuficiente ({stock_atual} disp.)."
            novo_stock = stock_atual - quantidade if tipo == "Saída" else stock_atual + quantidade
            con.execute("UPDATE pecas SET stock = ? WHERE id = ?", (novo_stock, peca_id))
        
        con.execute("INSERT INTO movimentos (peca_id, tipo, quantidade, maquina, observacoes, tecnico, data, imagem) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (peca_id, tipo, quantidade, maquina, observacoes, tecnico, datetime.now().isoformat(), imagem))
    
    enviar_para_nextbit({"tecnico": tecnico, "tipo": tipo, "maquina": maquina, "obs": observacoes})
    return True, "Registo efetuado com sucesso."

if "pagina_atual" not in st.session_state:
    st.session_state.pagina_atual = "📦 Stock"

col_top1, col_top2 = st.columns([3, 1])
with col_top1:
    st.markdown(f"<h3 style='margin: 0;'>⚡ OptiMaint — Wayzim & CTT</h3><p style='margin: 0; color: #38BDF8;'>Operador ativo: <b>{st.session_state.utilizador_atual}</b></p>", unsafe_allow_html=True)
with col_top2:
    if st.button("Sair da Sessão"):
        st.session_state.autenticado = False
        st.rerun()

st.divider()

eh_admin = (st.session_state.utilizador_atual == "Carlos Souza")
opcoes_menu = ["📦 Stock", "➕ Nova Peça", "🔄 Movimentos", "📝 Registar Preventiva", "📷 Leitor QR", "📋 Histórico & Relatórios"]
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
        termo = st.text_input("🔍 Pesquisar peça...", placeholder="Pesquisar...", label_visibility="collapsed")
    with col_f2:
        apenas_critico = st.checkbox("⚠️ Stock Baixo (≤2)")

    with ligar_base_dados() as con:
        df = pd.read_sql_query("SELECT id, codigo, nome, armazem, localizacao, stock, imagem FROM pecas ORDER BY codigo", con)

    if not df.empty:
        if termo:
            df = df[df["codigo"].str.contains(termo, case=False, na=False) | df["nome"].str.contains(termo, case=False, na=False)]
        if apenas_critico:
            df = df[df["stock"] <= LIMITE_STOCK_BAIXO]

        tab_alg, tab_rio = st.tabs(["Algoz", "Rio de Mouro"])
        
        def render_lista(sub_df):
            if sub_df.empty:
                st.markdown("<p style='color: #64748B;'>Nenhuma peça encontrada.</p>", unsafe_allow_html=True)
                return
            for _, r in sub_df.iterrows():
                c1, c2, c3, c4, c5 = st.columns([1.5, 2.5, 0.9, 0.8, 1.2])
                with c1:
                    img_val = r["imagem"]
                    if pd.notna(img_val) and str(img_val).strip() and os.path.exists(os.path.join(IMAGENS_DIR, str(img_val))):
                        st.image(os.path.join(IMAGENS_DIR, str(img_val)), width=130)
                    else:
                        st.markdown("<span style='color: #475569;'>Sem foto</span>", unsafe_allow_html=True)
                with c2:
                    st.markdown(f"<b>{r['codigo']}</b> — {r['nome']}<br><span style='color: #64748B;'>Loc: {r['localizacao'] or '—'}</span>", unsafe_allow_html=True)
                with c3:
                    cor = "#EF4444" if r["stock"] <= LIMITE_STOCK_BAIXO else "#22C55E"
                    st.markdown(f"<span style='color: {cor}; font-weight: bold;'>Qtd: {r['stock']}</span>", unsafe_allow_html=True)
                with c4:
                    with st.popover("📷 Foto"):
                        up_f = st.file_uploader(f"Atualizar foto", type=["png", "jpg", "jpeg"], key=f"f_{r['id']}")
                        if up_f and st.button("Guardar", key=f"b_{r['id']}"):
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
    st.markdown("<h3>Adicionar Nova Peça</h3>", unsafe_allow_html=True)
    arm = st.radio("Armazém", ["Algoz", "Rio de Mouro"], horizontal=True)
    col_n1, col_n2 = st.columns(2)
    with col_n1:
        cod = st.text_input("Código")
        loc = st.text_input("Localização")
    with col_n2:
        nom = st.text_input("Nome")
        qtd = st.number_input("Quantidade Inicial", min_value=0, step=1)
    foto = st.file_uploader("Foto", type=["png", "jpg", "jpeg"])

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
                st.success("Registada!")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("Código já existe.")

elif st.session_state.pagina_atual == "🔄 Movimentos":
    st.markdown("<h3>Registo de Saídas / Entradas</h3>", unsafe_allow_html=True)
    with ligar_base_dados() as con:
        opcoes = con.execute("SELECT id, codigo, nome, stock, armazem FROM pecas ORDER BY armazem, codigo").fetchall()
    
    if opcoes:
        indice_default = 0
        if "peca_selecionada_mov" in st.session_state:
            for idx, p in enumerate(opcoes):
                if p[0] == st.session_state["peca_selecionada_mov"]:
                    indice_default = idx
                    break
            del st.session_state["peca_selecionada_mov"]

        sel = st.selectbox("Peça", opcoes, index=indice_default, format_func=lambda p: f"[{p[4]}] {p[1]} — {p[2]} (Stock: {p[3]})")
        tp = st.radio("Tipo", ["Saída", "Entrada"], horizontal=True)
        qt = st.number_input("Quantidade", min_value=1, step=1)
        
        col_m1, col_m2 = st.columns(2)
        with col_m1: eq = st.selectbox("Equipamento", ["Singulator", "Sorter", "Carts", "Tapetes", "Outro"])
        with col_m2: det = st.text_input("Detalhe", placeholder="Ex: Cart 143")
        
        obs = st.text_area("Observações")
        if st.button("Confirmar Movimento"):
            suc, msg = registar_movimento(sel[0], tp, qt, f"{eq} — {det}" if det else eq, obs, st.session_state.utilizador_atual)
            if suc: st.success(msg); st.rerun()
            else: st.error(msg)

elif st.session_state.pagina_atual == "📝 Registar Preventiva":
    st.markdown("<h3>Registar Preventiva / Intervenção</h3>", unsafe_allow_html=True)
    col_p1, col_p2 = st.columns(2)
    with col_p1: sis = st.selectbox("Sistema", ["Singulator", "Sorter", "Carts", "Tapetes", "Linha Geral", "Outro"])
    with col_p2: det_p = st.text_input("Detalhe / Número", placeholder="Ex: Cart 202")
    
    obs_prev = st.text_area("Relatório / Notas")
    foto_prev = st.file_uploader("Fotografia da Intervenção", type=["png", "jpg", "jpeg"])

    if st.button("Guardar Relatório"):
        if not obs_prev:
            st.warning("Escreve uma nota.")
        else:
            img_nome = None
            if foto_prev:
                ext = foto_prev.name.split(".")[-1]
                img_nome = f"prev_{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}"
                with open(os.path.join(IMAGENS_DIR, img_nome), "wb") as f: f.write(foto_prev.getbuffer())
            
            suc, msg = registar_movimento(None, "Preventiva", 0, f"{sis} — {det_p}" if det_p else sis, obs_prev, st.session_state.utilizador_atual, imagem=img_nome)
            if suc: st.success("Preventiva guardada com sucesso!")
            else: st.error(msg)

elif st.session_state.pagina_atual == "📷 Leitor QR":
    st.markdown("<h3>Leitor QR e de Barras</h3>", unsafe_allow_html=True)
    st.caption("💡 Dica: Se a câmara não abrir após dar permissão, clica em 'Stock' e volta a abrir.")
    if LEITOR_DISPONIVEL:
        cam = st.camera_input("Capturar etiqueta")
        if cam:
            res = zxingcpp.read_barcodes(np.array(Image.open(cam).convert("RGB")))
            if res:
                c_lido = res[0].text.strip()
                with ligar_base_dados() as con:
                    peca = con.execute("SELECT id, codigo, nome, stock, armazem FROM pecas WHERE codigo = ? OR codigo_limpo = ?", 
                                       (c_lido.upper(), normalizar_codigo(c_lido))).fetchone()
                if peca:
                    st.success(f"Peça: {peca[2]}")
                    q_ret = st.number_input("Qtd a retirar", min_value=1, step=1)
                    if st.button("Registar Saída Imediata"):
                        registar_movimento(peca[0], "Saída", q_ret, "Leitor QR", "Leitura direta", st.session_state.utilizador_atual)
                        st.rerun()
                else:
                    st.error("Código não encontrado.")
            else:
                st.warning("Nenhum código detetado.")

elif st.session_state.pagina_atual == "📋 Histórico & Relatórios":
    st.markdown("<h3>Histórico e Emissão de Relatórios Oficiais</h3>", unsafe_allow_html=True)
    
    with ligar_base_dados() as con:
        df_h = pd.read_sql_query("""
            SELECT 
                strftime('%d/%m %H:%M', m.data) AS Data, 
                COALESCE(p.codigo, '—') AS Código, 
                COALESCE(p.nome, 'Preventiva') AS Item, 
                m.tipo AS Tipo, 
                m.quantidade AS Qtd, 
                m.tecnico AS Técnico, 
                m.maquina AS Equipamento, 
                m.observacoes AS Notas
            FROM movimentos m 
            LEFT JOIN pecas p ON p.id = m.peca_id 
            ORDER BY m.id DESC
        """, con)
    
    if not df_h.empty:
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            if st.button("📄 Gerar Relatório PDF Oficial"):
                pdf_bytes = gerar_pdf_relatorio("Manutenção e Armazém", df_h)
                st.download_button("📥 Descarregar PDF", data=pdf_bytes, file_name="relatorio_optimaint.pdf", mime="application/pdf")
        with col_r2:
            csv_data = df_h.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Descarregar CSV", data=csv_data, file_name="historico_optimaint.csv", mime="text/csv")
            
        st.dataframe(df_h, hide_index=True, use_container_width=True)
    else:
        st.info("ℹ️ Ainda não existem movimentos ou preventivas registadas. Faz um registo no menu 'Registar Preventiva' ou 'Movimentos' para começar a gerar relatórios oficiais.")

elif eh_admin and st.session_state.pagina_atual == "⚙️ Admin":
    st.markdown("<h3>Painel de Administração</h3>", unsafe_allow_html=True)
    with st.form("form_t"):
        n_nome = st.text_input("Nome Técnico")
        n_tel = st.text_input("Telemóvel (Password)")
        if st.form_submit_button("Guardar"):
            with ligar_base_dados() as con:
                con.execute("INSERT INTO tecnicos (nome, telemovel) VALUES (?, ?) ON CONFLICT(nome) DO UPDATE SET telemovel = excluded.telemovel", (n_nome, n_tel))
            st.success("Guardado!")
            st.rerun()

st.markdown("<div style='text-align: center; margin-top: 3rem; font-size: 0.75rem; color: #475569;'>OptiMaint Industrial Platform — Desenvolvido por Carlos Souza</div>", unsafe_allow_html=True)
