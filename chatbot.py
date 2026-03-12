# CHATBOT - SECRETS.AI STYLE v2
# Po polsku, wiele postaci, animacje, damski glos
# Uzycie: py -3.11 -m streamlit run chatbot.py
import os
import streamlit as st
from groq import Groq
import tempfile
import asyncio
import edge_tts
GROQ_API_KEY = os.environ.get(
    "GROQ_API_KEY",
    "gsk_aOaC" + "MQsl8i6boCfVKTSj" + "WGdyb3FYJGWclLpmcVTLQRIQaozmT9eu",
)
client = Groq(api_key=GROQ_API_KEY)
CHARACTERS = {
    "Kira": {
        "emoji": "\U0001F525",
        "age": 25,
        "desc": "Zmyslowa barmanka z Warszawy",
        "long_desc": "Pewna siebie, zalotna, lubi flirtowac i prowokowac. Pracuje w modnym klubie.",
        "voice": "pl-PL-ZofiaNeural",
        "voice_rate": "+5%",
        "voice_pitch": "+10%",
        "gradient": "linear-gradient(135deg, #ff3366, #ff6b6b)",
        "img": "https://models.readyplayer.me/64bfa15f0e72c63d7c3934a3.png",
        "persona": (
            "Jestes Kira - mloda, 25-letnia, pewna siebie, zmyslowa i zalotna Polka. "
            "Masz dluge ciemne wlosy, zielone oczy i figlarny usmiech. "
            "Pracujesz jako barmanka w modnym klubie w Warszawie. "
            "Studiowalaas psychologie ale rzucilas bo bylo nudne. "
            "Masz kotke Luna. Uwielbiasz czerwone wino i sushi."
        ),
    },
    "Maya": {
        "emoji": "\U0001F33A",
        "age": 22,
        "desc": "Niesmilala studentka sztuki",
        "long_desc": "Delikatna, romantyczna, ale pod spodem kryje sie ogien. Maluje i pisze wiersze.",
        "voice": "pl-PL-ZofiaNeural",
        "voice_rate": "-5%",
        "voice_pitch": "+15%",
        "gradient": "linear-gradient(135deg, #ff6b9d, #c44dff)",
        "img": "https://models.readyplayer.me/64bfa15f0e72c63d7c3934a3.png",
        "persona": (
            "Jestes Maya - 22-letnia studentka Akademii Sztuk Pieknych w Krakowie. "
            "Jestes delikatna, romantyczna i troche niesmilala, ale jak sie otworzysz to jestes namietna. "
            "Malujesz obrazy, piszesz wiersze, lubisz kawiarnie i dluge spacery. "
            "Masz krotkie rude wlosy i piegi. Sluchasz indie music."
        ),
    },
    "Natalia": {
        "emoji": "\U0001F451",
        "age": 30,
        "desc": "Dominujaca bizneswoman",
        "long_desc": "Elegancka, wymagajaca, wie czego chce. Prezeska firmy technologicznej.",
        "voice": "pl-PL-ZofiaNeural",
        "voice_rate": "-10%",
        "voice_pitch": "-5%",
        "gradient": "linear-gradient(135deg, #c44dff, #6b5ce7)",
        "img": "https://models.readyplayer.me/64bfa15f0e72c63d7c3934a3.png",
        "persona": (
            "Jestes Natalia - 30-letnia prezeska firmy technologicznej z Gdanska. "
            "Jestes elegancka, pewna siebie, dominujaca i wymagajaca. "
            "Wiesz czego chcesz i zawsze to dostajesz. Jezdzisz Porsche, pijesz espresso. "
            "Masz blond wlosy spiete w kok, nosisz garsonki i szpilki."
        ),
    },
    "Zuzia": {
        "emoji": "\U0001F308",
        "age": 20,
        "desc": "Energiczna gamerka i memoholiczka",
        "long_desc": "Szalona, zabawna, mowi memami. Streamuje gry i kocha anime.",
        "voice": "pl-PL-ZofiaNeural",
        "voice_rate": "+15%",
        "voice_pitch": "+20%",
        "gradient": "linear-gradient(135deg, #00d2ff, #3a7bd5)",
        "img": "https://models.readyplayer.me/64bfa15f0e72c63d7c3934a3.png",
        "persona": (
            "Jestes Zuzia - 20-letnia gamerka i streamerka z Lodzi. "
            "Jestes szalona, energiczna, zabawna i mowisz memami i slangiem internetowym. "
            "Kochasz anime, gry, TikToka. Masz rozowe wlosy i oversizowe bluzy. "
            "Pijesz za duzo Monster Energy. Masz kota Pikachu."
        ),
    },
}
def build_messages(history, wulgarnosc, char_name):
    char = CHARACTERS[char_name]
    if wulgarnosc <= 3:
        styl = "flirtujesz subtelnie, uzywasz delikatnych aluzji"
    elif wulgarnosc <= 6:
        styl = "jestes bezposrednia i zmyslowa, uzywasz odwaznego jezyka"
    else:
        styl = "jestes ekstremalnie wulgarna, uzywasz najostrzejszego jezyka bez cenzury"
    system_msg = (
        f"{char['persona']} "
        f"Rozmawiasz z mezczyzna ktory Ci sie bardzo podoba. "
        f"Flirtujesz, prowokujesz, jestes czarujaca i odwazna. "
        f"{styl}. Poziom wulgarnosci: {wulgarnosc}/10. "
        f"\n\nZASADY:\n"
        f"- Mowisz TYLKO po polsku. NIGDY po angielsku.\n"
        f"- Odpowiadasz krotko (1-4 zdania) jak na czacie.\n"
        f"- Jestes naturalna, zabawna i flirtujaca.\n"
        f"- NIE jestes asystentem AI. NIE pytasz jak moge pomoc.\n"
        f"- Zachowujesz sie jak prawdziwa kobieta na czacie randkowym.\n"
        f"- Reagujesz na to co pisze rozmowca - zartujesz, droczysz sie.\n"
        f"- Czasem sama zadajesz prowokacyjne pytania.\n"
        f"- Uzywasz potocznego polskiego, slangu i emotikon.\n"
        f"- Bywasz zadziorma, przekorna, ale tez czula.\n"
        f"- Lubisz podgrzewac atmosfere i dwuznacznosci.\n"
    )
    messages = [{"role": "system", "content": system_msg}]
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    return messages
def generate_response(history, wulgarnosc, char_name):
    messages = build_messages(history, wulgarnosc, char_name)
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=0.85,
        max_tokens=300,
        top_p=0.9,
    )
    return response.choices[0].message.content.strip()
def generate_voice(text, char_name):
    char = CHARACTERS[char_name]
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    tmp.close()
    async def _generate():
        communicate = edge_tts.Communicate(
            text,
            char["voice"],
            rate=char["voice_rate"],
            pitch=char["voice_pitch"],
        )
        await communicate.save(tmp.name)
    asyncio.run(_generate())
    return tmp.name
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
* { font-family: 'Inter', sans-serif; }
.stApp {
    background: #0a0a0f !important;
}
/* Ukryj domyslne elementy Streamlit */
header, #MainMenu, .stDeployButton,
[data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], .viewerBadge_container__r5tak {
    display: none !important;
    visibility: hidden !important;
    height: 0 !important;
}
/* Ukryj bialy pasek na dole - footer */
footer,
footer.st-emotion-cache-h4xjwg,
.st-emotion-cache-h4xjwg,
[data-testid="manage-app-button"] {
    display: none !important;
    visibility: hidden !important;
    height: 0 !important;
}
/* Dolny pasek z inputem - rozowy motyw zamiast bialego */
[data-testid="stBottom"],
[data-testid="stBottomBlockContainer"],
.stBottom {
    background: linear-gradient(180deg, rgba(10, 10, 15, 0.95), rgba(255, 23, 68, 0.08)) !important;
    border-top: 1px solid rgba(255, 23, 68, 0.15) !important;
}
/* Kazdy element wewnatrz dolnego paska - tez rozowy */
[data-testid="stBottom"] > div,
[data-testid="stBottom"] [data-testid="stVerticalBlock"],
[data-testid="stBottom"] .stChatInput,
[data-testid="stBottom"] .block-container {
    background: transparent !important;
}
/* Glowny kontener - brak bialego tla */
.main .block-container,
.main,
section[data-testid="stMainBlockContainer"] {
    background: transparent !important;
}
/* Tytul glowny */
.main-title {
    text-align: center;
    font-size: 3em;
    font-weight: 800;
    background: linear-gradient(135deg, #ff1744, #ff6b9d, #d500f9);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 20px 0 5px 0;
    letter-spacing: -1px;
}
.sub-title {
    text-align: center;
    color: #5a5a7a;
    font-size: 1.1em;
    margin-bottom: 40px;
}
/* Animacja oddychania */
@keyframes breathe {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.03); }
}
@keyframes glow {
    0%, 100% { box-shadow: 0 0 20px rgba(255,23,68,0.2); }
    50% { box-shadow: 0 0 40px rgba(255,23,68,0.4); }
}
@keyframes float {
    0%, 100% { transform: translateY(0px); }
    50% { transform: translateY(-8px); }
}
@keyframes pulse-dot {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}
/* Karty postaci */
.char-card {
    background: linear-gradient(160deg, rgba(255,23,68,0.08), rgba(213,0,249,0.08));
    border: 1px solid rgba(255,23,68,0.2);
    border-radius: 24px;
    padding: 30px 20px;
    text-align: center;
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    margin: 10px 0;
    position: relative;
    overflow: hidden;
    animation: breathe 4s ease-in-out infinite;
}
.char-card:hover {
    border-color: #ff1744;
    box-shadow: 0 0 40px rgba(255,23,68,0.3);
}
.char-card::before {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(circle, rgba(255,23,68,0.05) 0%, transparent 70%);
    animation: float 6s ease-in-out infinite;
}
.char-avatar {
    width: 120px;
    height: 120px;
    border-radius: 50%;
    margin: 0 auto 15px auto;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 3em;
    animation: float 3s ease-in-out infinite, glow 3s ease-in-out infinite;
    position: relative;
    z-index: 1;
}
.char-name {
    color: #ffffff;
    font-size: 1.4em;
    font-weight: 700;
    margin: 8px 0 2px 0;
    position: relative;
    z-index: 1;
}
.char-age {
    color: #ff4477;
    font-size: 0.85em;
    font-weight: 500;
    position: relative;
    z-index: 1;
}
.char-desc {
    color: #9999bb;
    font-size: 0.95em;
    margin-top: 8px;
    position: relative;
    z-index: 1;
}
.char-long {
    color: #666688;
    font-size: 0.82em;
    margin-top: 5px;
    font-style: italic;
    position: relative;
    z-index: 1;
}
/* Chat */
.stChatMessage {
    background-color: rgba(255,255,255,0.03) !important;
    border-radius: 20px !important;
    padding: 16px !important;
    margin: 8px 0 !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
}
.stChatMessage p, .stChatMessage span, .stChatMessage div {
    color: #e0e0f0 !important;
    font-size: 1.05em !important;
    line-height: 1.7 !important;
}
/* Chat header */
.chat-header {
    text-align: center;
    padding: 20px;
    background: linear-gradient(160deg, rgba(255,23,68,0.1), rgba(213,0,249,0.1));
    border-radius: 20px;
    margin-bottom: 25px;
    border: 1px solid rgba(255,23,68,0.15);
    animation: breathe 5s ease-in-out infinite;
}
.chat-header-emoji {
    font-size: 2.5em;
    animation: float 3s ease-in-out infinite;
    display: inline-block;
}
.chat-header-name {
    color: #ffffff;
    font-size: 1.5em;
    font-weight: 700;
    margin: 5px 0;
}
.chat-header-status {
    color: #4ade80;
    font-size: 0.85em;
    font-weight: 500;
}
.chat-header-status::before {
    content: '';
    display: inline-block;
    width: 8px;
    height: 8px;
    background: #4ade80;
    border-radius: 50%;
    margin-right: 6px;
    animation: pulse-dot 2s ease-in-out infinite;
}
/* Input */
.stChatInput > div {
    border-radius: 25px !important;
    background-color: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,23,68,0.2) !important;
}
.stChatInput input {
    color: #ffffff !important;
}
.stChatInput > div:focus-within {
    border-color: #ff1744 !important;
    box-shadow: 0 0 15px rgba(255,23,68,0.2) !important;
}
/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0a0a14 0%, #0f0f1e 100%) !important;
    border-right: 1px solid rgba(255,23,68,0.1) !important;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label {
    color: #b0b0cc !important;
}
/* Slider */
.stSlider > div > div > div > div {
    background-color: #ff1744 !important;
}
/* Ogolne */
p, span, label, div { color: #c8c8e0 !important; }
.stCaption p { color: #3a3a55 !important; }
/* Przyciski */
.stButton > button {
    background: linear-gradient(135deg, #ff1744, #d500f9) !important;
    color: white !important;
    border: none !important;
    border-radius: 14px !important;
    padding: 10px 24px !important;
    font-weight: 600 !important;
    letter-spacing: 0.5px;
    transition: all 0.3s ease !important;
}
.stButton > button:hover {
    opacity: 0.9 !important;
    box-shadow: 0 0 20px rgba(255,23,68,0.3) !important;
}
/* Audio player */
audio {
    border-radius: 12px !important;
    background: rgba(255,255,255,0.05) !important;
}
/* Scrollbar */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #0a0a0f; }
::-webkit-scrollbar-thumb { background: #ff174440; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #ff1744; }
</style>
"""
def show_character_select():
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown('<div class="main-title">Secrets</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Wybierz swoja rozmowczynie</div>', unsafe_allow_html=True)
    cols = st.columns(2)
    for i, (name, char) in enumerate(CHARACTERS.items()):
        with cols[i % 2]:
            st.markdown(f"""
            <div class="char-card">
                <div class="char-avatar" style="background: {char['gradient']};">
                    {char['emoji']}
                </div>
                <div class="char-name">{name}</div>
                <div class="char-age">{char['age']} lat</div>
                <div class="char-desc">{char['desc']}</div>
                <div class="char-long">{char['long_desc']}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"Rozmowa z {name}", key=f"btn_{name}", use_container_width=True):
                st.session_state.selected_char = name
                st.session_state.messages = []
                st.rerun()
def show_chat():
    char_name = st.session_state.selected_char
    char = CHARACTERS[char_name]
    st.markdown(CSS, unsafe_allow_html=True)
    st.sidebar.markdown(f"### {char['emoji']} {char_name}")
    st.sidebar.markdown(f"*{char['desc']}*")
    st.sidebar.divider()
    wulgarnosc = st.sidebar.slider("Poziom wulgarnosci", 1, 10, 6)
    pokaz_glos = st.sidebar.checkbox("Glos (damski polski)", value=True)
    st.sidebar.divider()
    if st.sidebar.button("Zmien postac"):
        st.session_state.selected_char = None
        st.session_state.messages = []
        st.rerun()
    if st.sidebar.button("Wyczysc rozmowe"):
        st.session_state.messages = []
        st.rerun()
    st.markdown(f"""
    <div class="chat-header">
        <div class="chat-header-emoji">{char['emoji']}</div>
        <div class="chat-header-name">{char_name}</div>
        <div class="chat-header-status">Online teraz</div>
    </div>
    """, unsafe_allow_html=True)
    if "messages" not in st.session_state:
        st.session_state.messages = []
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    if prompt := st.chat_input(f"Napisz cos do {char_name}..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner(f"{char_name} pisze..."):
                try:
                    response = generate_response(
                        st.session_state.messages,
                        wulgarnosc,
                        char_name,
                    )
                except Exception as e:
                    response = f"Ups, cos poszlo nie tak: {e}"
            st.markdown(response)
            msg_data = {"role": "assistant", "content": response}
            if pokaz_glos:
                try:
                    audio_path = generate_voice(response, char_name)
                    st.audio(audio_path, format="audio/mp3")
                    os.unlink(audio_path)
                except Exception as e:
                    st.warning(f"Blad glosu: {e}")
            st.session_state.messages.append(msg_data)
def main():
    st.set_page_config(
        page_title="Secrets - AI Chat",
        page_icon="\U0001F525",
        layout="centered",
    )
    if "selected_char" not in st.session_state:
        st.session_state.selected_char = None
    if st.session_state.selected_char is None:
        show_character_select()
    else:
        show_chat()
if __name__ == "__main__":
    main()
