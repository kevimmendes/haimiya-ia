# Arcana/Net/search_ddg.py (VERSÃO 2025 ATUALIZADA)
import json
import os
from ddgs import DDGS  # Novo pacote!

# 🔥 Alterado de #armazen para #cache
HISTORY_PATH = os.path.join("Arcana", "#cache", "pesquisa_ddg.json")
LINKS_PATH = os.path.join("Arcana", "#cache", "pesquisa_links.json")

# ==========================================
# 🧹 SISTEMA DE AUTO-LIMPEZA
# ==========================================
def limpar_cache_de_pesquisa():
    """Deleta os arquivos de cache toda vez que a IA é reiniciada."""
    for path in [HISTORY_PATH, LINKS_PATH]:
        if os.path.exists(path):
            try:
                os.remove(path)
                print(f"[SISTEMA] 🗑️ Cache de pesquisa deletado: {os.path.basename(path)}")
            except Exception as e:
                print(f"[SISTEMA] ⚠️ Erro ao deletar cache {path}: {e}")

# Executa a limpeza automaticamente quando o módulo é importado pelo run.py
limpar_cache_de_pesquisa()
# ==========================================


def load_history():
    if os.path.exists(HISTORY_PATH):
        try:
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_history(data):
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def save_links(query, links):
    os.makedirs(os.path.dirname(LINKS_PATH), exist_ok=True)
    all_links = {}
    if os.path.exists(LINKS_PATH):
        try:
            with open(LINKS_PATH, "r", encoding="utf-8") as f:
                all_links = json.load(f)
        except:
            pass
    all_links[query] = links
    with open(LINKS_PATH, "w", encoding="utf-8") as f:
        json.dump(all_links, f, indent=2, ensure_ascii=False)

def search_ddg(query):
    history = load_history()
    if query in history:
        print(f"(Cache) Usando resultado salvo: {query}")
        return history[query]

    print(f"(Web) Pesquisando: {query}")
    try:
        with DDGS() as ddgs:
            # Backend padrão + região BR + max 5 resultados
            results = list(ddgs.text(query, region="br-pt", max_results=5))
        
        if not results:
            return "Não achei nada útil... Tenta reformular?"

        formatted = []
        links = []
        for r in results:
            title = r.get("title", "").strip()
            body = r.get("body", "").strip()
            href = r.get("href", "")
            if title and body:  # Filtra vazios
                formatted.append(f"• {title}: {body[:200]}...")  # Limita pra não poluir
            if href:
                links.append(href)

        answer = "\n".join(formatted)
        save_links(query, links)
        history[query] = answer
        save_history(history)
        print(f"📄 Resultados salvos: {len(formatted)} itens")
        return answer

    except Exception as e:
        print(f"❌ Erro DDG: {e}")
        return "Busca falhou – internet zuada ou query esquisita. Tenta de novo?"