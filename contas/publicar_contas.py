"""Agenda no Buffer os posts de um dia para as contas de contas/contas.json.

Uso: python3 contas/publicar_contas.py amanha [conta] [--teste]
     python3 contas/publicar_contas.py 05/11 julio
Cada conta usa a própria chave (variável de ambiente indicada em 'chave'),
porque cada uma fica numa conta separada do Buffer. A café NÃO passa por aqui.
Contas com "ativa": false são ignoradas. Contas com "ia": true saem com o
rótulo de conteúdo gerado por IA do TikTok.
Precisa de VIDEO_BASE_URL (ex.: https://raw.githubusercontent.com/<dono>/<repo>/main).
"""
import json, os, sys, datetime, urllib.request

API = "https://api.buffer.com"
BRT = datetime.timezone(datetime.timedelta(hours=-3))
AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
CRIAR = """mutation($i: CreatePostInput!) { createPost(input: $i) {
  ... on PostActionSuccess { post { id dueAt } }
  ... on MutationError { message } } }"""


def gql(chave, query, variables=None):
    req = urllib.request.Request(
        API, json.dumps({"query": query, "variables": variables or {}}).encode(),
        {"Content-Type": "application/json", "Authorization": f"Bearer {chave}"})
    resp = json.load(urllib.request.urlopen(req, timeout=60))
    if resp.get("errors"):
        raise RuntimeError(f"Erro do Buffer: {resp['errors']}")
    return resp["data"]


def canal_tiktok(chave):
    """Cada conta do Buffer deve ter exatamente um canal TikTok."""
    orgs = gql(chave, "query { account { organizations { id } } }")["account"]["organizations"]
    achados = []
    for org in orgs:
        q = "query($o: OrganizationId!) { channels(input: {organizationId: $o}) { id service name } }"
        achados += [(org["id"], c["id"], c["name"]) for c in gql(chave, q, {"o": org["id"]})["channels"]
                    if c["service"].lower() == "tiktok"]
    if len(achados) != 1:
        raise RuntimeError(f"Esperava 1 canal TikTok nessa conta do Buffer, achei {len(achados)}: {achados}")
    return achados[0]


def ja_agendados(chave, org, canal, data):
    q = "query($i: PostsInput!) { posts(first: 50, input: $i) { edges { node { dueAt } } } }"
    i = {"organizationId": org, "filter": {"channelIds": [canal], "dueAt": {
        "start": f"{data:%Y-%m-%d}T00:00:00-03:00", "end": f"{data:%Y-%m-%d}T23:59:59-03:00"}}}
    return {f"{datetime.datetime.fromisoformat(e['node']['dueAt'].replace('Z', '+00:00')).astimezone(BRT):%H:%M}"
            for e in gql(chave, q, {"i": i})["posts"]["edges"]}


def video_existe(url):
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30)
        return True
    except Exception:
        return False


def data_alvo(arg):
    hoje = datetime.datetime.now(BRT).date()
    if arg == "amanha":
        return hoje + datetime.timedelta(days=1)
    d = datetime.datetime.strptime(f"{arg}/{hoje.year}", "%d/%m/%Y").date()
    return d if d >= hoje else d.replace(year=hoje.year + 1)


def agendar(nome, cfg, data, teste):
    leg_arq = os.path.join(RAIZ, cfg["pasta"], "legendas.json")
    legendas = json.load(open(leg_arq, encoding="utf-8")).get(f"{data:%d/%m}", {}) if os.path.exists(leg_arq) else {}
    if not legendas:
        print(f"[{nome}] sem legendas para {data:%d/%m}, nada a fazer")
        return 0
    chave = None if teste else os.environ.get(cfg["chave"])
    if not teste and not chave:
        print(f"[{nome}] variável {cfg['chave']} não definida")
        return 1
    org, canal, handle = (None, None, "?") if teste else canal_tiktok(chave)
    feitos = set() if teste else ja_agendados(chave, org, canal, data)
    base = os.environ.get("VIDEO_BASE_URL", "<VIDEO_BASE_URL>").rstrip("/")
    falhas = 0
    for slot, hora in cfg["horarios"].items():
        if slot not in legendas:
            continue
        if hora in feitos:
            print(f"[{nome}] {hora} já agendado, pulando")
            continue
        url = f"{base}/{cfg['pasta']}/{data:%m}/{data:%d-%m}.{slot}.mp4"
        if not teste and not video_existe(url):
            print(f"[{nome}] {hora} vídeo não encontrado: {url}")
            falhas += 1
            continue
        entrada = {"channelId": canal, "text": legendas[slot], "schedulingType": "automatic",
                   "mode": "customScheduled", "needsApproval": False,
                   "dueAt": f"{data:%Y-%m-%d}T{hora}:00-03:00", "assets": [{"video": {"url": url}}]}
        if cfg.get("ia"):
            entrada["metadata"] = {"tiktok": {"isAiGenerated": True}}
        if teste:
            print(f"[{nome}]", json.dumps(entrada, ensure_ascii=False))
            continue
        r = gql(chave, CRIAR, {"i": entrada})["createPost"]
        falhas += 0 if r.get("post") else 1
        print(f"[{nome}/@{handle}] {hora}", r.get("post") or r.get("message"))
    return falhas


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    teste = "--teste" in sys.argv
    data = data_alvo(args[0])
    contas = json.load(open(os.path.join(AQUI, "contas.json"), encoding="utf-8"))["contas"]
    alvo = args[1:] or [n for n, c in contas.items() if c.get("ativa")]
    falhas = 0
    for nome in alvo:  # uma conta com erro não impede as outras
        try:
            falhas += agendar(nome, contas[nome], data, teste)
        except Exception as e:
            print(f"[{nome}] falhou: {e}")
            falhas += 1
    if falhas:
        raise SystemExit(f"{falhas} falha(s).")


if __name__ == "__main__":
    main()
