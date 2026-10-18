"""Agenda no Buffer os 3 posts de um dia (07h, 12h, 21h, horário de Brasília).

Uso: python3 publicar_buffer.py 19/10 [--teste]
     python3 publicar_buffer.py amanha     (dia seguinte no horário de Brasília)
Precisa de:
  BUFFER_API_KEY   chave pessoal do Buffer (variável de ambiente, nunca no código)
  VIDEO_BASE_URL   endereço público onde os vídeos do dia já estão hospedados,
                   ex.: https://raw.githubusercontent.com/<dono>/<repo>/main
--teste só mostra o que seria enviado, sem chamar o Buffer.
"""
import json, os, sys, datetime, urllib.request, openpyxl

API = "https://api.buffer.com"
PLANILHA = os.environ.get("PLANILHA", "/mnt/project-files/plano/lancamento-fe/videos-365/legendas-365.xlsx")
SLOTS = [("07:00", 2, 3), ("12:00", 4, 5), ("21:00", 6, 7)]  # hora, col. arquivo, col. legenda
BRT = datetime.timezone(datetime.timedelta(hours=-3))


def gql(query, variables=None):
    req = urllib.request.Request(
        API, json.dumps({"query": query, "variables": variables or {}}).encode(),
        {"Content-Type": "application/json",
         "Authorization": f"Bearer {os.environ['BUFFER_API_KEY']}"})
    resp = json.load(urllib.request.urlopen(req, timeout=60))
    if resp.get("errors"):
        raise SystemExit(f"Erro do Buffer: {resp['errors']}")
    return resp["data"]


def canal_tiktok():
    orgs = gql("query { account { organizations { id } } }")["account"]["organizations"]
    for org in orgs:
        q = "query($o: OrganizationId!) { channels(input: {organizationId: $o}) { id service } }"
        for c in gql(q, {"o": org["id"]})["channels"]:
            if c["service"].lower() == "tiktok":
                return org["id"], c["id"]
    raise SystemExit("Nenhum canal do TikTok conectado no Buffer.")


def ja_agendados(org, canal, data):
    """Horários (HH:MM, Brasília) que já têm post do canal nesse dia, para não duplicar."""
    q = """query($i: PostsInput!) { posts(first: 50, input: $i) { edges { node { dueAt status } } } }"""
    ini = f"{data:%Y-%m-%d}T00:00:00-03:00"
    fim = f"{data:%Y-%m-%d}T23:59:59-03:00"
    i = {"organizationId": org, "filter": {"channelIds": [canal], "dueAt": {"start": ini, "end": fim}}}
    horas = set()
    for e in gql(q, {"i": i})["posts"]["edges"]:
        due = datetime.datetime.fromisoformat(e["node"]["dueAt"].replace("Z", "+00:00"))
        horas.add(f"{due.astimezone(BRT):%H:%M}")
    return horas


CRIAR = """mutation($i: CreatePostInput!) { createPost(input: $i) {
  ... on PostActionSuccess { post { id dueAt } }
  ... on MutationError { message } } }"""


def video_existe(url):
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30)
        return True
    except Exception:
        return False


def main():
    hoje = datetime.datetime.now(BRT).date()
    if sys.argv[1] == "amanha":
        data = hoje + datetime.timedelta(days=1)
    else:  # dd/mm: próxima ocorrência a partir de hoje
        data = datetime.datetime.strptime(f"{sys.argv[1]}/{hoje.year}", "%d/%m/%Y").date()
        if data < hoje:
            data = data.replace(year=hoje.year + 1)
    teste = "--teste" in sys.argv
    ws = openpyxl.load_workbook(PLANILHA, read_only=True)["Legendas"]
    linha = next(r for r in ws.iter_rows(min_row=2, values_only=True) if r[0] == f"{data:%d/%m}")
    org, canal = (None, None) if teste else canal_tiktok()
    feitos = set() if teste else ja_agendados(org, canal, data)
    base = os.environ.get("VIDEO_BASE_URL", "<VIDEO_BASE_URL>").rstrip("/")
    falhas = 0
    for hora, c_arq, c_leg in SLOTS:
        if hora in feitos:
            print(hora, "já agendado, pulando")
            continue
        url = f"{base}/{linha[c_arq]}"
        if not teste and not video_existe(url):
            print(hora, "vídeo não encontrado:", url)
            falhas += 1
            continue
        entrada = {
            "channelId": canal, "text": linha[c_leg],
            "schedulingType": "automatic", "mode": "customScheduled",
            "needsApproval": False,
            "dueAt": f"{data:%Y-%m-%d}T{hora}:00-03:00",
            "assets": [{"video": {"url": url}}],
        }
        if teste:
            print(json.dumps(entrada, ensure_ascii=False, indent=1))
            continue
        r = gql(CRIAR, {"i": entrada})["createPost"]
        if not r.get("post"):
            falhas += 1
        print(hora, r.get("post") or r.get("message"))
    if falhas:
        raise SystemExit(f"{falhas} post(s) não agendado(s).")


if __name__ == "__main__":
    main()
