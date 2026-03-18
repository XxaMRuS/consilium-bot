import os
import requests
import logging
import google.generativeai as genai
from collections import deque
from dotenv import load_dotenv

load_dotenv()

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# === ФЛАГИ ВКЛЮЧЕНИЯ ПРОВАЙДЕРОВ ===
ENABLED_PROVIDERS = {
    "openrouter": True,
    "groq": True,
    "yandex": True,
    "deepseek_old": False,
    "gemini_old": False,
}

if not all([YANDEX_API_KEY, YANDEX_FOLDER_ID, DEEPSEEK_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY, GROQ_API_KEY]):
    raise ValueError("❌ Не все ключи найдены в .env! Проверь файл.")

# === НАСТРОЙКА ЛОГИРОВАНИЯ ===
logging.basicConfig(
    filename='consilium.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger('').addHandler(console)

REQUEST_TIMEOUT = (10, 30)

# === АКТУАЛЬНЫЕ БЕСПЛАТНЫЕ МОДЕЛИ OPENROUTER ===
FREE_MODELS = [
    "stepfun/step-3.5-flash:free",
    "arcee-ai/trinity-large-preview:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "z-ai/glm-4.5-air:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "arcee-ai/trinity-mini:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
    "nvidia/nemotron-nano-9b-v2:free",
    "qwen/qwen3-coder:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "openai/gpt-oss-120b:free",
    "liquid/lfm-2.5-1.2b-thinking:free",
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "google/gemma-3-27b-it:free",
    "qwen/qwen3-4b:free",
    "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
    "meta-llama/llama-3.2-3b-instruct:free",
    "google/gemma-3-4b-it:free",
    "minimax/minimax-m2.5:free",
    "google/gemma-3-12b-it:free",
    "google/gemma-3n-e4b-it:free",
    "google/gemma-3n-e2b-it:free",
    "nvidia/llama-nemotron-embed-vl-1b-v2:free",
    "openrouter/free"
]

# === ИСТОРИЯ ДИАЛОГА УДАЛЕНА – БУДЕТ ХРАНИТЬСЯ В context.user_data ===
# (глобальная переменная history удалена)

# === СТАТИСТИКА ===
stats = {
    "attempts": 0,
    "success": 0,
    "failures": 0,
    "models_used": {}
}

def log_error(context, error):
    logging.error(f"{context}: {error}")

def log_info(message):
    logging.info(message)

def update_stats(success, model_name=None):
    stats["attempts"] += 1
    if success:
        stats["success"] += 1
        if model_name:
            stats["models_used"][model_name] = stats["models_used"].get(model_name, 0) + 1
    else:
        stats["failures"] += 1

# === OPENROUTER ===
def ask_openrouter(text, system_prompt=None, role_name="unknown"):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "AI Consilium"
    }
    last_error = None
    for model in FREE_MODELS:
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": text})
            data = {"model": model, "messages": messages}
            response = requests.post(url, json=data, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            result = response.json()
            content = result['choices'][0]['message']['content']
            log_info(f"OpenRouter {role_name} использовал {model}")
            update_stats(True, model)
            return content
        except Exception as e:
            last_error = e
            log_error(f"OpenRouter {role_name} {model} ошибка", e)
            update_stats(False, model)
            continue
    raise Exception(f"Все OpenRouter модели недоступны: {last_error}")

# === GROQ ===
def ask_groq(text, system_prompt=None, role_name="unknown"):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    models = [
        "llama-3.3-70b-versatile",
        "mixtral-8x7b-32768",
        "gemma2-9b-it"
    ]
    last_error = None
    for model in models:
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": text})
            data = {
                "model": model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 4000
            }
            response = requests.post(url, json=data, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            content = response.json()['choices'][0]['message']['content']
            log_info(f"Groq {role_name} использовал {model}")
            update_stats(True, f"Groq/{model}")
            return content
        except Exception as e:
            last_error = e
            log_error(f"Groq {role_name} {model} ошибка", e)
            update_stats(False, f"Groq/{model}")
            continue
    raise Exception(f"Все Groq модели недоступны: {last_error}")

# === ЯНДЕКС ===
def ask_yandex(text):
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}"}
    data = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite",
        "completionOptions": {"stream": False, "temperature": 0.6, "maxTokens": 2000},
        "messages": [{"role": "user", "text": text}]
    }
    try:
        response = requests.post(url, json=data, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        res_json = response.json()
        content = res_json['result']['alternatives'][0]['message']['text']
        log_info("Yandex успешно ответил")
        update_stats(True, "YandexGPT")
        return content
    except Exception as e:
        log_error("Yandex error", e)
        update_stats(False, "YandexGPT")
        raise

# === СТАРЫЙ DEEPSEEK (запасной) ===
def ask_deepseek(text):
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": text}]
    }
    try:
        response = requests.post(url, json=data, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        content = response.json()['choices'][0]['message']['content']
        log_info("DeepSeek успешно ответил")
        update_stats(True, "DeepSeek (old)")
        return content
    except Exception as e:
        log_error("DeepSeek error", e)
        update_stats(False, "DeepSeek (old)")
        raise

# === СТАРЫЙ GEMINI (запасной) ===
def ask_gemini(text):
    client = genai.Client(api_key=GEMINI_API_KEY)
    try:
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=text
        )
        content = response.text
        log_info("Gemini успешно ответил")
        update_stats(True, "Gemini (old)")
        return content
    except Exception as e:
        log_error("Gemini error", e)
        update_stats(False, "Gemini (old)")
        raise

# === УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ===
def ask_any_ai(text, system_prompt=None, role_name="unknown"):
    if ENABLED_PROVIDERS["openrouter"]:
        try:
            return ask_openrouter(text, system_prompt, role_name)
        except Exception as e:
            log_error(f"OpenRouter {role_name} failed", e)

    if ENABLED_PROVIDERS["groq"]:
        try:
            return ask_groq(text, system_prompt, role_name)
        except Exception as e:
            log_error(f"Groq {role_name} failed", e)

    if ENABLED_PROVIDERS["yandex"]:
        try:
            full_text = text
            if system_prompt:
                full_text = f"{system_prompt}\n\n{text}"
            return ask_yandex(full_text)
        except Exception as e:
            log_error(f"Yandex {role_name} failed", e)

    if ENABLED_PROVIDERS["deepseek_old"]:
        try:
            full_text = text
            if system_prompt:
                full_text = f"{system_prompt}\n\n{text}"
            return ask_deepseek(full_text)
        except Exception as e:
            log_error(f"DeepSeek(old) {role_name} failed", e)

    if ENABLED_PROVIDERS["gemini_old"]:
        try:
            full_text = text
            if system_prompt:
                full_text = f"{system_prompt}\n\n{text}"
            return ask_gemini(full_text)
        except Exception as e:
            log_error(f"Gemini(old) {role_name} failed", e)

    raise Exception("Все включённые AI недоступны")

# === ПОЛУЧЕНИЕ ПЕРВИЧНОГО ОТВЕТА (теперь принимает user_history) ===
def get_primary_answer(question, user_history):
    context = ""
    if user_history:
        context = "Предыдущий диалог:\n"
        for i, (q, a) in enumerate(user_history, 1):
            context += f"Вопрос {i}: {q}\nОтвет {i}: {a}\n"
        context += "\n"
    full_question = context + question if context else question
    try:
        ans = ask_any_ai(full_question, role_name="primary")
        return ans, "auto"
    except Exception as e:
        log_error("Все AI недоступны для primary", e)
        return None, None

def get_analysis(question, primary_answer, primary_source):
    prompt = f"Вопрос пользователя: {question}\nОтвет ({primary_source}): {primary_answer}\nПроверь этот ответ и предложи улучшения, укажи на возможные ошибки или добавь важные детали."
    try:
        ans = ask_any_ai(prompt, role_name="analyst")
        return ans
    except Exception as e:
        log_error("Analysis failed (все AI недоступны)", e)
        return None

def get_synthesis(question, primary_answer, primary_source, analysis=None):
    if analysis:
        prompt = f"Вопрос: {question}\nМнение 1 (от {primary_source}): {primary_answer}\nМнение 2 (анализ): {analysis}\nОбъедини оба мнения в один идеальный ответ. Будь полезным и точным."
    else:
        prompt = f"Вопрос: {question}\nОтвет (от {primary_source}): {primary_answer}\nУлучши этот ответ, сделай его более полным и понятным."
    try:
        ans = ask_any_ai(prompt, role_name="synthesizer")
        return ans
    except Exception as e:
        log_error("Synthesis failed (все AI недоступны)", e)
        return primary_answer

def print_stats():
    print("\n--- СТАТИСТИКА РАБОТЫ КОНСИЛИУМА ---")
    print(f"Всего попыток запросов: {stats['attempts']}")
    print(f"Успешно: {stats['success']}")
    print(f"Ошибок: {stats['failures']}")
    print("Использованные модели:")
    for model, count in stats['models_used'].items():
        print(f"  {model}: {count} раз(а)")
    print("------------------------------------\n")

# === ГЛАВНАЯ ФУНКЦИЯ (теперь принимает user_history) ===
def start_consilium(question, user_history):
    log_info(f"Новый запрос: {question}")
    primary_answer, primary_source = get_primary_answer(question, user_history)
    if not primary_answer:
        print_stats()
        return "❌ Не удалось получить ответ ни от одного AI."

    analysis = get_analysis(question, primary_answer, primary_source)
    final_answer = get_synthesis(question, primary_answer, primary_source, analysis)

    # Добавляем в историю пользователя
    user_history.append((question, final_answer))
    
    print_stats()
    return final_answer
