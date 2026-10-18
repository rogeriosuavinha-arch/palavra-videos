"""Agenda no Buffer os 3 posts de um dia (07h, 12h, 21h, horário de Brasília).

Uso: python3 publicar_buffer.py 19/10 [--teste]
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
ANO = 2026


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
                return c["id"]
    raise SystemExit("Nenhum canal do TikTok conectado no Buffer.")


CRIAR = """mutation($i: CreatePostInput!) { createPost(input: $i) {
  ... on PostActionSuccess { post { id dueAt } }
  ... on MutationError { message } } }"""


def main():
    data = datetime.datetime.strptime(f"{sys.argv[1]}/{ANO}", "%d/%m/%Y").date()
    teste = "--teste" in sys.argv
    ws = openpyxl.load_workbook(PLANILHA, read_only=True)["Legendas"]
    linha = next(r for r in ws.iter_rows(min_row=2, values_only=True) if r[0] == f"{data:%d/%m}")
    canal = None if teste else canal_tiktok()
    base = os.environ.get("VIDEO_BASE_URL", "<VIDEO_BASE_URL>").rstrip("/")
    for hora, c_arq, c_leg in SLOTS:
        entrada = {
            "channelId": canal, "text": linha[c_leg],
            "schedulingType": "automatic", "mode": "customScheduled",
            "dueAt": f"{data:%Y-%m-%d}T{hora}:00-03:00",
            "assets": [{"video": {"url": f"{base}/{linha[c_arq]}"}}],
        }
        if teste:
            print(json.dumps(entrada, ensure_ascii=False, indent=1))
            continue
        r = gql(CRIAR, {"i": entrada})["createPost"]
        print(hora, r.get("post") or r.get("message"))


if __name__ == "__main__":
    main()
