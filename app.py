import io, json, re, tempfile, os
from urllib.parse import urlparse
import requests
from PIL import Image, ImageOps
from flask import Flask, request, render_template_string, send_file, jsonify
app=Flask(__name__)
app.config["MAX_CONTENT_LENGTH"]=12*1024*1024
S=requests.Session(); S.headers.update({'User-Agent':'Mozilla/5.0 (compatible; ManuscriptResearchDownloader/1.0)', 'Accept':'application/json,image/*;q=0.9,*/*;q=0.8'})

def get(url):
    r=S.get(url,timeout=50);r.raise_for_status();return r

def candidates(link):
    u=urlparse(link.strip());
    if u.scheme!='https' or u.hostname!='tecabml.contentdm.oclc.org': raise ValueError('Inserisci un indirizzo HTTPS della piattaforma tecabml.contentdm.oclc.org')
    m=re.search(r'/digital/collection/([^/]+)/id/(\d+)',u.path)
    if m:
        a,i=m.groups();return [f'https://{u.hostname}/iiif/2/{a}:{i}/manifest.json',f'https://{u.hostname}/iiif/info/{a}/{i}/manifest.json']
    if u.path.endswith('manifest.json'):return [link.strip()]
    raise ValueError('Link non riconosciuto: serve /digital/collection/NOME/id/NUMERO')

def manifest(link):
    errors=[]
    for url in candidates(link):
        try:
            j=get(url).json()
            if j.get('sequences') or j.get('items'):return j,url
            errors.append(f'{url}: nessuna sequenza di immagini')
        except Exception as e:errors.append(f'{url}: {e}')
    raise RuntimeError('Manifest non accessibile. '+' | '.join(errors))

def text_label(x):
    if isinstance(x,str):return x
    if isinstance(x,dict):
        if '@value' in x:return str(x['@value'])
        return ' '.join(str(z) for vals in x.values() for z in (vals if isinstance(vals,list) else [vals]) if isinstance(z,str))
    return ''

def extract(j):
    out=[]
    if j.get('sequences'):
        for c in j['sequences'][0].get('canvases',[]):
            for ann in c.get('images',[]):
                res=ann.get('resource',{});svc=res.get('service',{})
                if isinstance(svc,list):svc=svc[0] if svc else {}
                base=svc.get('@id') or svc.get('id') if isinstance(svc,dict) else None
                direct=res.get('@id') or res.get('id')
                if base or direct:out.append((text_label(c.get('label')) or str(len(out)+1),base,direct))
    else:
        for c in j.get('items',[]):
            for annpage in c.get('items',[]):
                for ann in annpage.get('items',[]):
                    body=ann.get('body',{});body=body[0] if isinstance(body,list) else body
                    svc=body.get('service',[]);svc=svc[0] if isinstance(svc,list) and svc else svc
                    base=(svc.get('id') or svc.get('@id')) if isinstance(svc,dict) else None
                    direct=body.get('id') or body.get('@id')
                    if base or direct:out.append((text_label(c.get('label')) or str(len(out)+1),base,direct))
    return out

def download_image(base,direct,quality):
    urls=[]
    if base:
        base=base.rstrip('/')
        if quality=='Originale':sizes=['full','max','3000,','2000,']
        elif quality=='Alta':sizes=['3000,','2000,','1500,']
        elif quality=='Media':sizes=['1500,','1000,']
        else:sizes=['800,','600,']
        for size in sizes:
            urls.extend([f'{base}/full/{size}/0/default.jpg',f'{base}/full/{size}/0/native.jpg'])
    if direct:urls.append(direct)
    error='';
    for url in dict.fromkeys(urls):
        try:
            r=get(url)
            im=Image.open(io.BytesIO(r.content));im.load()
            im=ImageOps.exif_transpose(im)
            if im.mode!='RGB':im=im.convert('RGB')
            return im
        except Exception as e:error=str(e)
    raise RuntimeError(error or 'Immagine non disponibile')


HTML="""<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Laurenziana PDF Downloader</title><style>
*{box-sizing:border-box}body{margin:0;background:#f7faf7;color:#22372a;font:16px system-ui,-apple-system,sans-serif}.wrap{max-width:730px;margin:45px auto;padding:0 18px}h1{text-align:center;color:#216b46;font-size:30px;margin:0 0 8px}.subtitle{text-align:center;color:#64786b;margin:0 0 32px}.card{background:white;border:1px solid #dce8df;border-radius:13px;padding:25px;box-shadow:0 3px 16px #173b2510}label{display:block;font-weight:600;margin:18px 0 7px}input,select{width:100%;padding:12px;border:1px solid #b9cfc0;border-radius:8px;font:inherit;background:white}button,.download{display:block;text-align:center;width:100%;padding:13px 16px;border:0;border-radius:8px;background:#267a50;color:white;font:600 16px system-ui;cursor:pointer;text-decoration:none;margin-top:14px}button:hover,.download:hover{background:#175d3a}.secondary{background:#e7f3eb;color:#1b6942}.secondary:hover{background:#d6e9dd}.sep{border-top:1px solid #e2ebe5;margin:25px 0}.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}.note{color:#6a7e70;font-size:13px}.status{font-size:14px;color:#286b46;white-space:pre-wrap;margin-top:10px}.error{color:#a33434}h2{font-size:18px;color:#205d3c;margin:0 0 10px}
</style></head><body><main class="wrap"><h1>Laurenziana PDF Downloader</h1><p class="subtitle">Scarica i manoscritti della Biblioteca Medicea Laurenziana in PDF</p><div class="card"><h2>Manoscritto</h2><label for="url">Link del manoscritto</label><input id="url" value="https://tecabml.contentdm.oclc.org/digital/collection/plutei/id/146289/rec/1"><button onclick="fetchManifest()">Genera manifest JSON</button><div id="msg" class="status"></div><a id="jsonDownload" class="download secondary" style="display:none">Scarica manifest JSON</a><div class="sep"></div><h2>Oppure carica un manifest JSON</h2><input id="file" type="file" accept=".json,application/json"><div class="sep"></div><h2>Genera PDF</h2><p id="count" class="note">Genera o carica un manifest per iniziare.</p><label for="quality">Qualità delle immagini</label><select id="quality"><option>Originale</option><option selected>Alta</option><option>Media</option><option>Bassa</option></select><div class="row"><div><label for="start">Da pagina</label><input id="start" type="number" min="1" value="1"></div><div><label for="end">A pagina</label><input id="end" type="number" min="1" value="1"></div></div><button onclick="makePdf()">Scarica PDF</button><div id="pdfmsg" class="status"></div><p class="note">Per manoscritti molto grandi potrebbe essere necessario scaricare più intervalli.</p></div></main><script>
let manifestData=null;
function setManifest(m){manifestData=m;let n=pageCount(m);document.getElementById('count').textContent='Pagine disponibili: '+n;document.getElementById('end').value=n;document.getElementById('end').max=n;document.getElementById('start').max=n;let blob=new Blob([JSON.stringify(m,null,2)],{type:'application/json'});let a=document.getElementById('jsonDownload');if(a.dataset.url)URL.revokeObjectURL(a.dataset.url);a.dataset.url=URL.createObjectURL(blob);a.href=a.dataset.url;a.download='laurenziana_manifest.json';a.style.display='block'}
function pageCount(m){if(m.sequences)return (m.sequences[0].canvases||[]).length;return (m.items||[]).length}
async function fetchManifest(){let e=document.getElementById('msg');e.textContent='Recupero manifest...';try{let r=await fetch('/manifest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:document.getElementById('url').value})});let j=await r.json();if(!r.ok)throw Error(j.error);setManifest(j.manifest);e.textContent='Manifest pronto.'}catch(err){e.textContent='Errore: '+err.message}}
document.getElementById('file').addEventListener('change',async e=>{try{let m=JSON.parse(await e.target.files[0].text());setManifest(m);document.getElementById('msg').textContent='Manifest caricato.'}catch(err){document.getElementById('msg').textContent='JSON non valido: '+err.message}});
async function makePdf(){let msg=document.getElementById('pdfmsg');if(!manifestData){msg.textContent='Prima genera o carica un manifest.';return}msg.textContent='Generazione PDF in corso...';try{let r=await fetch('/pdf',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({manifest:manifestData,quality:document.getElementById('quality').value,start:Number(document.getElementById('start').value),end:Number(document.getElementById('end').value)})});if(!r.ok){let j=await r.json();throw Error(j.error)}let blob=await r.blob();let url=URL.createObjectURL(blob);let a=document.createElement('a');a.href=url;a.download='laurenziana_'+document.getElementById('start').value+'-'+document.getElementById('end').value+'.pdf';a.click();setTimeout(()=>URL.revokeObjectURL(url),60000);msg.textContent='Download avviato.'}catch(err){msg.textContent='Errore: '+err.message}}
</script></body></html>"""
@app.get("/")
def index(): return render_template_string(HTML)
@app.post("/manifest")
def manifest_route():
    try:
        j,url=manifest((request.get_json() or {}).get("url",""))
        return jsonify(manifest=j,url=url)
    except Exception as e:return jsonify(error=str(e)),400
@app.post("/pdf")
def pdf_route():
    try:
        args=request.get_json()
        pages=extract(args["manifest"])
        start=int(args["start"]);end=int(args["end"])
        if not 1<=start<=end<=len(pages):raise ValueError("Intervallo pagine non valido")
        if end-start+1>150:raise ValueError("Seleziona al massimo 150 pagine per PDF per evitare limiti di memoria")
        quality=args.get("quality","Alta")
        if quality not in ("Originale","Alta","Media","Bassa"):raise ValueError("Qualità non valida")
        imgs=[];errors=[]
        for idx,(label,base,direct) in enumerate(pages[start-1:end],start):
            try:imgs.append(download_image(base,direct,quality))
            except Exception as e:errors.append(f"{idx} ({label}): {e}")
        if errors:raise RuntimeError("Immagini non disponibili: "+"; ".join(errors[:4]) + (f" (e altre {len(errors)-4})" if len(errors)>4 else ""))
        if not imgs:raise ValueError("Nessuna immagine trovata")
        output=io.BytesIO()
        imgs[0].save(output,format="PDF",save_all=True,append_images=imgs[1:],resolution=150)
        output.seek(0)
        return send_file(output,mimetype="application/pdf",as_attachment=True,download_name=f"laurenziana_{start}-{end}.pdf")
    except Exception as e:return jsonify(error=str(e)),400
if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.environ.get("PORT",10000)))
