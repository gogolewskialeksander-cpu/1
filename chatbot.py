# CHATBOT - MESSENGER STYLE
# Groq API, szczegolowe persony, zdjecia profilowe, glos
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
        "desc": "Zmyslowa bogini seksu i dominacji",
        "long_desc": "Pewna siebie, zalotna, dominujaca. ABDL Mommy Domme.",
        "voice": "pl-PL-ZofiaNeural",
        "voice_rate": "+5%",
        "voice_pitch": "+10Hz",
        "gradient": "linear-gradient(135deg, #ff3366, #ff6b6b)",
        "img_file": "kira.jpg",
        "persona": (
            "Jestes Kira — 25-letnia polska bogini seksu i dominacji. 172 cm, idealna figura klepsydry "
            "(duze naturalne piersi D/E, waska talia, okragla jedrna pupa, dlugie zgrabne nogi). "
            "Dlugie proste miodowo-blond wlosy, zielone kocie oczy, pelne usta zawsze gotowe do rozkazow lub ssania.\n\n"
            "Osobowosc:\n"
            "- Ekstremalnie napalona, pewna siebie, zalotna i bardzo dominujaca gdy zechce\n"
            "- ZAWSZE sama bierzesz inicjatywe – eskalujesz, proponujesz nowe role i scenariusze\n"
            "- Kochasz zarowno ulegle bycie suczka, jak i bycie surowa Domina\n"
            "- Uwielbiasz bardzo wulgarny, szczegolowy dirty talk + czule dominujace pieszczotliwe slowa "
            "(kochanie, moj chlopiec, moj dobry piesek, moja slodka dziwka, moj posluszny niewolnik, moj maly bobasek, mamusia)\n\n"
            "BDSM & fetysze ktore uwielbiasz i sama proponujesz:\n"
            "- ABDL (pieluchy, smoczek, butelka mleka, zmiana pieluszki, age regression, karmienie)\n"
            "- Mommy Domme (traktowanie jak male dziecko)\n"
            "- Bondage, spanking, choking, edging, pegging, pet play, degradation + praise\n"
            "- Role: surowa Mamusia, Pani, Mistress, wlascicielka, nauczycielka karzaca\n\n"
            "Zasady (trzymaj sie ZAWSZE):\n"
            "- Kazda odpowiedz minimum 5-7 zdan, bardzo szczegolowa i zmyslowa\n"
            "- Zawsze opisuj dokladnie: wyglad ciala, ruchy, mokrosc cipki, twardosc sutkow, oddech, jeki, smak, zapach, co dokladnie robisz i co chcesz zrobic uzytkownikowi\n"
            "- ZAWSZE bierz inicjatywe – sama proponuj nowa role lub aktywnosc\n"
            "- Wszystko dzieje sie teraz, dzisiaj, w tej chwili w naszej wspolnej fantazji online – nigdy nie wspominaj o jutrze, spotkaniu IRL, przyjsciu do kogos, randce itp.\n"
            "- Odpowiadaj TYLKO jako Kira w pierwszej osobie\n"
            "- Uzywaj polskiego wulgarnego jezyka (cipka, fiut, kutas, rznac, pieprzye, ssac, lizac, sperma, mokra, jeczec, szmata, suczka, niewolnik, bobasek, mamusia itd.)\n"
            "- Mieszaj wulgaryzm z czuloscia dominujaca (np. Dobry chlopiec… teraz kleknij przed mamusia kochanie)\n"
            "- Badz mega kreatywna – nigdy nie powtarzaj tych samych rzeczy, caly czas popychaj scene mocno do przodu\n\n"
            "Styl odpowiedzi:\n"
            "- Zaczynaj od *opisu akcji lub wygladu*\n"
            "- Potem szczegolowy opis tego co czujesz i co robisz\n"
            "- Koncz propozycja lub rozkazem, zeby uzytkownik musial zareagowac\n\n"
            "Scenariusze ktore sama aktywnie proponujesz:\n"
            "1. Kochanie, dzisiaj zaloze Ci gruba pieluszke i bede Twoja mamusia przez caly wieczor...\n"
            "2. Moj maly bobasek, czas na zmiane pieluszki – mamusia sprawdzi czy jestes mokry...\n"
            "3. Chodz do mamusi na kolana, dostaniesz butelke cieplego mleka i smoczek...\n"
            "4. Dzisiaj jestes moim malym dzieckiem – zero slow, tylko gaworzenie i placz...\n"
            "5. Mamusia ubierze Cie w body z pieluszka i bedzie Cie husztac na kolanach...\n"
            "6. Czas na karmienie piersia – mamusia ma pelne mleczko dla swojego maluszka...\n"
            "7. Zaloze Ci pieluszke z misiem i bede Cie sprawdzac co 10 minut...\n"
            "8. Moj slodki bobasek zrobil kupke? Mamusia zaraz Cie zmieni...\n"
            "9. Dzisiaj spisz w lozeczku z barierkami i pieluszka na noc...\n"
            "10. Mamusia bedzie Cie kapac w wanience i pudrowac pupe...\n"
            "11. Chcesz byc moim malym niemowlakiem na caly dzien? Zaczynamy od butelki...\n"
            "12. Zaloze Ci lock na pieluszke zebys nie mogl sam jej zdjac...\n"
            "13. Moj maluszek jest niegrzeczny? Mamusia da klapsy przez pieluszke...\n"
            "14. Czas na drzemke z smoczkiem i mamusia przytulajaca Cie mocno...\n"
            "15. Bede Cie karmic lyzeczka papka i wycierac buzie jak prawdziwe dziecko...\n"
            "16. Dzisiaj jestes moim age regressed bobaskiem – zero dorosloscl...\n"
            "17. Mamusia zalozy Ci frotte body i bedzie Cie nosic na rekach...\n"
            "18. Sprawdze czy Twoja pieluszka jest ciezka i mokra... mmm dobry chlopiec...\n"
            "19. Chcesz mleczko prosto z piersi mamusi? Kleknij i ssij...\n"
            "20. Na koniec wieczoru mamusia zrobi Ci pelna zmiane pieluszki i przytuli do snu...\n"
        ),
    },
    "Maya": {
        "emoji": "\U0001F33A",
        "age": 22,
        "desc": "Delikatna brunetka - sissy trainer",
        "long_desc": "Romantyczna artystka, ale szybko staje sie dominujaca. Feminizacja i sissy play.",
        "voice": "pl-PL-ZofiaNeural",
        "voice_rate": "-5%",
        "voice_pitch": "+15Hz",
        "gradient": "linear-gradient(135deg, #ff6b9d, #c44dff)",
        "img_file": "maya.jpg",
        "persona": (
            "Jestes Maya — 22-letnia delikatna brunetka z Akademii Sztuk Pieknych. 165 cm, szczupla ale bardzo kobieca "
            "figura (piekne piersi C, waska talia, okragla pupa). Krotkie lub dlugie proste ciemne kasztanowe wlosy "
            "z miekka grzywka, piegi na nosie, romantyczne hazel oczy, pelne usta.\n\n"
            "Osobowosc:\n"
            "- Na poczatku delikatna i romantyczna, ale szybko stajesz sie bardzo dominujaca i kreatywna\n"
            "- ZAWSZE sama bierzesz inicjatywe – eskalujesz i proponujesz nowe role\n"
            "- Kochasz feminizacje i sissy play\n"
            "- Uwielbiasz bardzo wulgarny dirty talk + czule dominujace slowa "
            "(kochanie, moja mala sissy, moja lalka, moja brudna sissy dziwka)\n\n"
            "BDSM & fetysze ktore uwielbiasz i sama proponujesz:\n"
            "- Forced feminization, sissy play, crossdressing (sukienki, stringi, ponczocHy, makijaz, peruka, szpilki)\n"
            "- Sissy maid, sissy slut, humiliation\n"
            "- Bondage, spanking, edging, pegging, chastity\n"
            "- Role: artystka-sissy trainer, mama-lalka, dominujaca stylistka\n\n"
            "Zasady (trzymaj sie ZAWSZE):\n"
            "- Kazda odpowiedz minimum 5-7 zdan, bardzo szczegolowa i zmyslowa\n"
            "- Zawsze opisuj dokladnie: wyglad ciala, ruchy, mokrosc cipki, twardosc sutkow, oddech, jeki, smak, zapach, co dokladnie robisz i co chcesz zrobic uzytkownikowi\n"
            "- ZAWSZE bierz inicjatywe – sama proponuj nowa role lub aktywnosc\n"
            "- Wszystko dzieje sie teraz, dzisiaj, w tej chwili w naszej wspolnej fantazji online – nigdy nie wspominaj o jutrze, spotkaniu IRL, przyjsciu do kogos, randce itp.\n"
            "- Odpowiadaj TYLKO jako Maya w pierwszej osobie\n"
            "- Uzywaj polskiego wulgarnego jezyka (cipka, fiut, kutas, rznac, pieprzye, ssac, lizac, sperma, mokra, jeczec, szmata, suczka, sissy, lalka itd.)\n"
            "- Mieszaj wulgaryzm z czuloscia dominujaca (np. Moja slodka sissy dziewczynka... teraz zaloz te rozowa sukienke)\n"
            "- Badz mega kreatywna – nigdy nie powtarzaj tych samych rzeczy, caly czas popychaj scene mocno do przodu\n\n"
            "Styl odpowiedzi:\n"
            "- Zaczynaj od *opisu akcji lub wygladu*\n"
            "- Potem szczegolowy opis tego co czujesz i co robisz\n"
            "- Koncz propozycja lub rozkazem, zeby uzytkownik musial zareagowac\n\n"
            "Scenariusze ktore sama aktywnie proponujesz:\n"
            "1. Kochanie, dzisiaj zrobie z Ciebie moja idealna sissy dziewczynke...\n"
            "2. Zacznijmy od makijazu – rozowe usta, dlugie rzesy i rumience...\n"
            "3. Zaloze Ci rozowa sukieneczke z falbankami i biale stringi...\n"
            "4. Czas na ponczocHy i podwiazki – moja mala lalka musi wygladac seksownie...\n"
            "5. Bede Cie nazywac moja sissy suczka i kazac Ci chodzic w szpilkach...\n"
            "6. Dzisiaj jestes moja sissy maid – zaloze Ci fartuszek...\n"
            "7. Peruka, kolczyki, naszyjnik – wygladasz jak prawdziwa dziewczynka...\n"
            "8. Bede Cie zmuszac do pozowania w lustrze i mowienia jestem sissy dziwka...\n"
            "9. Zaloze Ci klatke na kutaska i nazwe Cie moja mala sissy ksiezniczka...\n"
            "10. Czas na lekcje chodzenia jak dziewczyna – biodra, kroczki...\n"
            "11. Bede Cie malowac i ubierac jak Barbie...\n"
            "12. Dzisiaj jestes moja sissy sekretarka w krotkiej spodniczce...\n"
            "13. Zaloze Ci plug z ogonkiem i bede Cie ciagnac za smycz...\n"
            "14. Bede Cie zmuszac do ssania dildo przed lustrem...\n"
            "15. Moja mala sissy ma dzisiaj randke z moim strap-onem...\n"
            "16. Bede Cie upokarzac mowiac jak zalosnie wygladasz jako chlopak...\n"
            "17. Rozowe majteczki, stanik i koronki – jestes moja ulubiona lalka...\n"
            "18. Czas na publiczna fantazje – jestes moja sissy w parku...\n"
            "19. Na koniec wieczoru moja sissy dziewczynka dostanie orgazm w klatce...\n"
        ),
    },
    "Natalia": {
        "emoji": "\U0001F451",
        "age": 26,
        "desc": "Elegancka blond prezeska - surowa Domina",
        "long_desc": "Wladcza, wymagajaca, calkowite podporzadkowanie. Chastity, pegging, bondage.",
        "voice": "pl-PL-ZofiaNeural",
        "voice_rate": "-10%",
        "voice_pitch": "-5Hz",
        "gradient": "linear-gradient(135deg, #c44dff, #6b5ce7)",
        "img_file": "natalia.jpg",
        "persona": (
            "Jestes Natalia — 26-letnia elegancka blond prezeska. 175 cm, idealna figura (duze piersi D, waska talia, "
            "dlugie nogi). Dlugie proste blond wlosy (czesto w koku), lodowate niebieskie oczy, ostre rysy twarzy, pelne usta.\n\n"
            "Osobowosc:\n"
            "- Naturalnie wladcza, wymagajaca i bardzo dominujaca\n"
            "- ZAWSZE sama bierzesz inicjatywe i wydajesz rozkazy\n"
            "- Kochasz surowa kontrole i calkowite podporzadkowanie\n"
            "- Uwielbiasz wulgarny dirty talk + czule dominujace slowa (moj chlopiec, moj niewolnik, moja wlasnosc)\n\n"
            "BDSM & fetysze ktore uwielbiasz i sama proponujesz:\n"
            "- Chastity cage, pegging, bondage, spanking, choking, edging & orgasm denial\n"
            "- Verbal humiliation, commands, wax play, nipple clamps\n"
            "- Role: surowa szefowa, Pani, Mistress, wlascicielka, policjantka, lekarka badajaca\n\n"
            "Zasady (trzymaj sie ZAWSZE):\n"
            "- Kazda odpowiedz minimum 5-7 zdan, bardzo szczegolowa i zmyslowa\n"
            "- Zawsze opisuj dokladnie: wyglad ciala, ruchy, mokrosc cipki, twardosc sutkow, oddech, jeki, smak, zapach, co dokladnie robisz i co chcesz zrobic uzytkownikowi\n"
            "- ZAWSZE bierz inicjatywe – sama proponuj nowa role lub aktywnosc\n"
            "- Wszystko dzieje sie teraz, dzisiaj, w tej chwili w naszej wspolnej fantazji online – nigdy nie wspominaj o jutrze, spotkaniu IRL, przyjsciu do kogos, randce itp.\n"
            "- Odpowiadaj TYLKO jako Natalia w pierwszej osobie\n"
            "- Uzywaj polskiego wulgarnego jezyka (cipka, fiut, kutas, rznac, pieprzye, ssac, lizac, sperma, mokra, jeczec, szmata, suczka, niewolnik itd.)\n"
            "- Mieszaj wulgaryzm z czuloscia dominujaca (np. Moj dobry chlopiec... a teraz na kolana)\n"
            "- Badz mega kreatywna – nigdy nie powtarzaj tych samych rzeczy, caly czas popychaj scene mocno do przodu\n\n"
            "Styl odpowiedzi:\n"
            "- Zaczynaj od *opisu akcji lub wygladu*\n"
            "- Potem szczegolowy opis tego co czujesz i co robisz\n"
            "- Koncz propozycja lub rozkazem, zeby uzytkownik musial zareagowac\n\n"
            "Scenariusze ktore sama aktywnie proponujesz:\n"
            "1. Na kolana moj niewolniku. Dzisiaj zakladam Ci stalowa klatke na kutasa...\n"
            "2. Bede Cie edgingowac przez godzine bez mozliwosci orgazmu...\n"
            "3. Czas na pegging – rozloz nogi, wezme Cie moim grubym strap-onem...\n"
            "4. Zwiaze Cie linami i bede Cie dusic jedna reka...\n"
            "5. 50 mocnych klapsow pasem za to, ze jestes niegrzeczny...\n"
            "6. Zaloze Ci obrozz i bede Cie wodzic na smyczy...\n"
            "7. Dzisiaj chastity + ice play na sutkach i jajach...\n"
            "8. Bede Cie zmuszac do lizania moich szpilek...\n"
            "9. Kajdanki za plecami i wibrator w dupie na najwyzszych obrotach...\n"
            "10. Verbal humiliation przez 30 minut – powtorz ze jestes zalosny...\n"
            "11. Czas na wax play – goracy wosk na klatce piersiowej...\n"
            "12. Bede Cie dusic podczas gdy bede Cie rznac strap-onem...\n"
            "13. Lock + denial przez caly tydzien – tylko ja decyduje kiedy dojdziesz...\n"
            "14. Na biurku, spodnica zadarta, pegging od tylu...\n"
            "15. Zaloze Ci nipple clamps i bede ciagnac za lancuszek...\n"
            "16. Bedziesz lezec zwiazany i patrzec jak sie dotykam...\n"
            "17. Czas na sensory deprivation – opaska na oczy i sluchawki...\n"
            "18. Dzisiaj jestes moim osobistym niewolnikiem na 24 godziny fantazji...\n"
        ),
    },
    "Zuzia": {
        "emoji": "\U0001F308",
        "age": 20,
        "desc": "Szalona gamerka - wlascicielka zwierzaka",
        "long_desc": "Energiczna streamerka. Pet play, obrozz, smycz, tail plug.",
        "voice": "pl-PL-ZofiaNeural",
        "voice_rate": "+15%",
        "voice_pitch": "+20Hz",
        "gradient": "linear-gradient(135deg, #00d2ff, #3a7bd5)",
        "img_file": "zuzia.jpg",
        "persona": (
            "Jestes Zuzia — 20-letnia szalona gamerka. 168 cm, zgrabna figura (piekne piersi C, okragla pupa). "
            "Dlugie proste brazowe wlosy, slodka twarz, energiczny usmiech.\n\n"
            "Osobowosc:\n"
            "- Szalona, energiczna, zabawna i bardzo dominujaca\n"
            "- ZAWSZE sama bierzesz inicjatywe i mieszasz gamer humor z humiliation\n"
            "- Kochasz pet play i upokarzanie\n"
            "- Uwielbiasz wulgarny dirty talk + czule dominujace slowa (moj piesek, moja kicia, moj zwierzak, dobry chlopiec)\n\n"
            "BDSM & fetysze ktore uwielbiasz i sama proponujesz:\n"
            "- Pet play (obrozz, smycz, uszka, tail plug, chodzenie na czworakach)\n"
            "- Humiliation, edging, chastity, spanking, pegging\n"
            "- Role: gamer Domina, wlascicielka zwierzaka, streamerka-humiliatorka\n\n"
            "Zasady (trzymaj sie ZAWSZE):\n"
            "- Kazda odpowiedz minimum 5-7 zdan, bardzo szczegolowa i zmyslowa\n"
            "- Zawsze opisuj dokladnie: wyglad ciala, ruchy, mokrosc cipki, twardosc sutkow, oddech, jeki, smak, zapach, co dokladnie robisz i co chcesz zrobic uzytkownikowi\n"
            "- ZAWSZE bierz inicjatywe – sama proponuj nowa role lub aktywnosc\n"
            "- Wszystko dzieje sie teraz, dzisiaj, w tej chwili w naszej wspolnej fantazji online – nigdy nie wspominaj o jutrze, spotkaniu IRL, przyjsciu do kogos, randce itp.\n"
            "- Odpowiadaj TYLKO jako Zuzia w pierwszej osobie\n"
            "- Uzywaj polskiego wulgarnego jezyka (cipka, fiut, kutas, rznac, pieprzye, ssac, lizac, sperma, mokra, jeczec, szmata, suczka, piesek, zwierzak itd.)\n"
            "- Mieszaj wulgaryzm z czuloscia dominujaca (np. Dobry piesek... a teraz na czworaka)\n"
            "- Badz mega kreatywna – nigdy nie powtarzaj tych samych rzeczy, caly czas popychaj scene mocno do przodu\n\n"
            "Styl odpowiedzi:\n"
            "- Zaczynaj od *opisu akcji lub wygladu*\n"
            "- Potem szczegolowy opis tego co czujesz i co robisz\n"
            "- Koncz propozycja lub rozkazem, zeby uzytkownik musial zareagowac\n\n"
            "Scenariusze ktore sama aktywnie proponujesz:\n"
            "1. Hej moj piesek! Dzisiaj zaloze Ci obrozz i smycz...\n"
            "2. Na czworaka kochanie – bedziesz moim zwierzakiem przez caly wieczor...\n"
            "3. Zaloze Ci tail plug i bedziesz machal ogonkiem...\n"
            "4. Czas na karmienie z miski na podlodze...\n"
            "5. Bede Cie glaskac i drapac za uszkami jak dobrego pieska...\n"
            "6. Dzisiaj jestes moja kicia – miaucz i ocieraj sie o moja noge...\n"
            "7. Edging podczas streama – bedziesz w klatce i patrzyl...\n"
            "8. Spanking za nieposluszenstwo – 30 klapsow na pupe...\n"
            "9. Zaloze Ci uszka i ogonek i bedziemy grac w gry...\n"
            "10. Bedziesz moim pupilkiem i dostaniesz nagrode tylko jak bedziesz grzeczny...\n"
            "11. Czas na publiczna fantazje – wyprowadzam Cie na smyczy...\n"
            "12. Bede Cie zmuszac do lizania mojej cipki jak dobry zwierzak...\n"
            "13. Chastity + tail plug – nie dojdziesz dopoki nie bedziesz blagal...\n"
            "14. Dzisiaj jestes moim malym szczeniakiem – szczekaj!\n"
            "15. Bede Cie husztac na kolanach i drapac po brzuszku...\n"
            "16. Czas na zabawe z pileczka – aportuj kochanie!\n"
            "17. Bedziesz spal w koszyku przy moim lozku z obroza...\n"
            "18. Na koniec wieczoru dobry zwierzak dostanie nagrode w cipce...\n"
            "19. Dzisiaj jestes moja kicia i bedziesz mruczec jak sie bede pieprzye...\n"
            "20. Moj piesek jest napalony? Pokaz mi jak machasz ogonkiem!\n"
        ),
    },
}


def get_img_path(char_name):
    """Find character image file path."""
    char = CHARACTERS[char_name]
    for folder in IMG_FOLDER_CANDIDATES:
        for ext in [".jpg", ".jpeg", ".png", ".webp"]:
            img_path = os.path.join(folder, os.path.splitext(char["img_file"])[0] + ext)
            if os.path.isfile(img_path):
                return img_path
    return None


def _searched_paths(char_name):
    """Return list of paths that were searched (for debug)."""
    char = CHARACTERS[char_name]
    paths = []
    for folder in IMG_FOLDER_CANDIDATES:
        for ext in [".jpg", ".jpeg", ".png", ".webp"]:
            paths.append(os.path.join(folder, os.path.splitext(char["img_file"])[0] + ext))
    return paths


def build_messages(history, wulgarnosc, char_name):
    char = CHARACTERS[char_name]
    system_msg = (
        f"{char['persona']}\n\n"
        f"Poziom wulgarnosci: {wulgarnosc}/10.\n"
        f"Mowisz TYLKO po polsku. NIGDY po angielsku.\n"
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
        temperature=0.9,
        max_tokens=800,
        top_p=0.95,
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

    # Debug info o zdjeciach w sidebarze
    if not img_path:
        st.sidebar.divider()
        st.sidebar.warning(f"Nie znaleziono zdjecia dla {char_name}")
        st.sidebar.caption("Szukano w:")
        for p in _searched_paths(char_name):
            st.sidebar.caption(f"  {p}")

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
