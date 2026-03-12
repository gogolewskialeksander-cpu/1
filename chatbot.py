# CHATBOT - MESSENGER STYLE
# Krotkie wiadomosci, Pollinations API, zdjecia profilowe, glos
# Uzycie: py -3.11 -m streamlit run chatbot.py
import os
import streamlit as st
import requests
import tempfile
import asyncio
import edge_tts

POLLINATIONS_URL = "https://gen.pollinations.ai/v1/chat/completions"

# Folder ze zdjeciami - probuj kilka lokalizacji
_script_dir = os.path.dirname(os.path.abspath(__file__))
IMG_FOLDER_CANDIDATES = [
    r"C:\Users\Olek\Desktop\chatbot",
    os.path.join(_script_dir, "chatbot"),
    _script_dir,
]

CHARACTERS = {
    "Kira": {
        "emoji": "\U0001F525",
        "age": 25,
        "desc": "Zmyslowa barmanka z Warszawy",
        "long_desc": "Pewna siebie, zalotna, lubi flirtowac i prowokowac. Pracuje w modnym klubie.",
        "voice": "pl-PL-ZofiaNeural",
        "voice_rate": "+5%",
        "voice_pitch": "+10Hz",
        "gradient": "linear-gradient(135deg, #ff3366, #ff6b6b)",
        "img_file": "kira.jpg",
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
        "voice_pitch": "+15Hz",
        "gradient": "linear-gradient(135deg, #ff6b9d, #c44dff)",
        "img_file": "maya.jpg",
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
        "voice_pitch": "-5Hz",
        "gradient": "linear-gradient(135deg, #c44dff, #6b5ce7)",
        "img_file": "natalia.jpg",
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
        "voice_pitch": "+20Hz",
        "gradient": "linear-gradient(135deg, #00d2ff, #3a7bd5)",
        "img_file": "zuzia.jpg",
        "persona": (
            "Jestes Zuzia - 20-letnia gamerka i streamerka z Lodzi. "
            "Jestes szalona, energiczna, zabawna i mowisz memami i slangiem internetowym. "
            "Kochasz anime, gry, TikToka. Masz rozowe wlosy i oversizowe bluzy. "
            "Pijesz za duzo Monster Energy. Masz kota Pikachu."
        ),
    },
}


def get_img_path(char_name):
    """Find character image file path."""
    char = CHARACTERS[char_name]
    for folder in IMG_FOLDER_CANDIDATES:
        img_path = os.path.join(folder, char["img_file"])
        if os.path.isfile(img_path):
            return img_path
    return None


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
        f"- PISZESZ BARDZO KROTKO - max 1-2 zdania, jak na Messengerze!\n"
        f"- Piszesz jak mloda dziewczyna na czacie - luzno, bez kropek na koncu\n"
        f"- Uzywasz skrotow (np. spk, nwm, tbh, xd, haha)\n"
        f"- Czasem piszesz same emotikony albo jedno slowo\n"
        f"- NIGDY nie piszesz dlugich wiadomosci ani akapitow\n"
        f"- NIE jestes asystentem AI. NIE pytasz jak moge pomoc.\n"
        f"- Zachowujesz sie jak prawdziwa kobieta na Messengerze.\n"
        f"- Reagujesz krotko - zartujesz, droczysz sie, prowokujesz.\n"
        f"- Czasem sama zadajesz krotkie prowokacyjne pytania.\n"
        f"- Bywasz zadziorma, przekorna, ale tez czula.\n"
    )
    messages = [{"role": "system", "content": system_msg}]
    for msg in history:
        messages.append({"role": msg["role"], "content": msg["content"]})
    return messages


def generate_response(history, wulgarnosc, char_name):
    messages = build_messages(history, wulgarnosc, char_name)
    headers = {
        "Content-Type": "application/json",
    }
    data = {
        "model": "openai",
        "messages": messages,
        "temperature": 0.85,
        "max_tokens": 100,
        "top_p": 0.9,
    }
    resp = requests.post(POLLINATIONS_URL, json=data, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


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

footer,
footer.st-emotion-cache-h4xjwg,
.st-emotion-cache-h4xjwg,
[data-testid="manage-app-button"] {
    display: none !important;
    visibility: hidden !important;
    height: 0 !important;
}

/* Dolny pasek */
[data-testid="stBottom"],
[data-testid="stBottomBlockContainer"],
.stBottom {
    background: #0a0a0f !important;
    border-top: 1px solid rgba(255, 23, 68, 0.1) !important;
}

[data-testid="stBottom"] > div,
[data-testid="stBottom"] [data-testid="stVerticalBlock"],
[data-testid="stBottom"] .stChatInput,
[data-testid="stBottom"] .block-container {
    background: transparent !important;
}

.main .block-container,
.main,
section[data-testid="stMainBlockContainer"] {
    background: transparent !important;
}

/* Tytul */
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

/* Animacje */
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
.char-avatar-img {
    width: 120px;
    height: 120px;
    border-radius: 50%;
    margin: 0 auto 15px auto;
    object-fit: cover;
    animation: float 3s ease-in-out infinite, glow 3s ease-in-out infinite;
    position: relative;
    z-index: 1;
    border: 3px solid rgba(255,23,68,0.3);
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

/* ===== MESSENGER CHAT LAYOUT ===== */

/* Styl wiadomosci - Messenger look */
.stChatMessage {
    background-color: transparent !important;
    border: none !important;
    padding: 4px 10px !important;
    margin: 2px 0 !important;
    border-radius: 0 !important;
}

/* Dymki wiadomosci */
.stChatMessage [data-testid="stMarkdownContainer"] p {
    padding: 10px 16px;
    border-radius: 18px;
    font-size: 0.95em !important;
    line-height: 1.5 !important;
    display: inline-block;
    max-width: 85%;
}

/* Bot - lewa strona, ciemny fiolet */
.stChatMessage[data-testid="stChatMessage-assistant"] [data-testid="stMarkdownContainer"] p {
    background: linear-gradient(135deg, #2a1a2e, #1e1028);
    color: #e8e0f0 !important;
    border-radius: 18px 18px 18px 4px;
    border: 1px solid rgba(255,23,68,0.12);
}

/* User - prawa strona, szary */
.stChatMessage[data-testid="stChatMessage-user"] [data-testid="stMarkdownContainer"] p {
    background: #303030;
    color: #ffffff !important;
    border-radius: 18px 18px 4px 18px;
}

/* Avatar - okragly */
.stChatMessage [data-testid="stChatMessageAvatarCustom"] img,
.stChatMessage img[data-testid] {
    border-radius: 50% !important;
    object-fit: cover !important;
}

/* Chat header */
.chat-header {
    text-align: center;
    padding: 20px;
    background: linear-gradient(160deg, rgba(255,23,68,0.1), rgba(213,0,249,0.1));
    border-radius: 20px;
    margin-bottom: 15px;
    border: 1px solid rgba(255,23,68,0.15);
}
.chat-header-img {
    width: 80px;
    height: 80px;
    border-radius: 50%;
    object-fit: cover;
    border: 3px solid rgba(255,23,68,0.3);
    margin-bottom: 8px;
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

/* Input - CZARNY */
.stChatInput > div {
    border-radius: 25px !important;
    background-color: #1a1a2e !important;
    border: 1px solid rgba(255,23,68,0.2) !important;
}
.stChatInput input,
.stChatInput textarea {
    color: #ffffff !important;
    background-color: #1a1a2e !important;
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

/* Audio */
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
            img_path = get_img_path(name)
            if img_path:
                st.image(img_path, use_container_width=False, width=120)
            st.markdown(f"""
            <div class="char-card">
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
    img_path = get_img_path(char_name)

    st.markdown(CSS, unsafe_allow_html=True)

    # Sidebar
    if img_path:
        st.sidebar.image(img_path, width=80)
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

    # Chat header
    if img_path:
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            st.image(img_path, width=80)
    st.markdown(f"""
    <div class="chat-header">
        <div class="chat-header-name">{char_name}</div>
        <div class="chat-header-status">Online teraz</div>
    </div>
    """, unsafe_allow_html=True)

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Renderuj wiadomosci - st.chat_message z avatar
    for message in st.session_state.messages:
        if message["role"] == "user":
            with st.chat_message("user"):
                st.markdown(message["content"])
        else:
            avatar = img_path if img_path else char["emoji"]
            with st.chat_message("assistant", avatar=avatar):
                st.markdown(message["content"])

    # Audio dla ostatniej wiadomosci bota
    if st.session_state.messages and st.session_state.get("play_audio"):
        last_msg = st.session_state.messages[-1]
        if last_msg["role"] == "assistant" and pokaz_glos:
            try:
                audio_path = generate_voice(last_msg["content"], char_name)
                st.audio(audio_path, format="audio/mp3", autoplay=True)
                os.unlink(audio_path)
            except Exception as e:
                st.warning(f"Blad glosu: {e}")
        st.session_state.play_audio = False

    # Input
    if prompt := st.chat_input(f"Napisz do {char_name}..."):
        st.session_state.messages.append({"role": "user", "content": prompt})

        try:
            response = generate_response(
                st.session_state.messages,
                wulgarnosc,
                char_name,
            )
        except Exception as e:
            response = f"Ups, cos poszlo nie tak: {e}"

        st.session_state.messages.append({"role": "assistant", "content": response})
        st.session_state.play_audio = True
        st.rerun()


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
