import io, os, re, time, uuid, threading, tempfile
from pathlib import Path
from urllib.parse import urlparse
import requests
from PIL import Image, ImageOps
from flask import Flask, request, jsonify, send_file, render_template_string
app=Flask(__name__)
app.config["MAX_CONTENT_LENGTH"]=2*1024*1024
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


HTML=r"""<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Laurenziana · PDF Downloader</title>
<style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:#19352a;background:#f5f8f5}
*{box-sizing:border-box}body{margin:0}.top{padding:19px max(24px,calc((100vw - 980px)/2));border-bottom:1px solid #dfe9e0;background:white;font-size:14px;font-weight:700;letter-spacing:.035em;color:#276749}
main{max-width:850px;margin:0 auto;padding:75px 24px}.eyebrow{font-size:12px;font-weight:750;letter-spacing:.18em;text-transform:uppercase;color:#3a9062}
h1{font-size:clamp(34px,5.5vw,56px);line-height:1.12;letter-spacing:-.045em;margin:16px 0 20px;color:#173d2a}
.intro{font-size:17px;color:#5a7062;line-height:1.7;max-width:680px;margin-bottom:37px}.panel{background:white;border:1px solid #dce9df;box-shadow:0 15px 55px #173b2510;border-radius:17px;padding:32px}
label{display:block;font-weight:680;margin-bottom:11px;font-size:14px}input,select{border:1px solid #cbdacf;border-radius:9px;background:#fff;padding:14px;font-size:15px;color:#244a34;width:100%}input:focus,select:focus{outline:2px solid #8fc8a5}
.hint{font-size:13px;color:#7b8d80;margin:11px 0 25px;line-height:1.55}
.actions{display:flex;align-items:end;gap:16px}.select{flex:1}.primary{background:#237a4b;color:white;border:0;border-radius:9px;padding:15px 23px;font-size:15px;font-weight:700;cursor:pointer;white-space:nowrap}.primary:hover{background:#155e38}.primary:disabled{opacity:.5;cursor:not-allowed}
.secondary{background:white;border:1px solid #b5cdbb;color:#226642;border-radius:9px;padding:12px 19px;font-size:14px;font-weight:700;cursor:pointer}
#progressArea{display:none;margin-top:25px;border-top:1px solid #e2ece5;padding-top:22px}.status{font-size:14px;margin:12px 0;color:#38694a}progress{width:100%;height:13px;accent-color:#26844f}
a.file{display:none;color:#176a40;font-weight:700;margin-top:15px}.foot{font-size:13px;color:#7b8c80;line-height:1.7;margin-top:24px}
@media(max-width:570px){main{padding:45px 16px}.panel{padding:22px}.actions{flex-direction:column;align-items:stretch}.select{width:100%}}
</style></head><body><header class="top">LAURENZIANA · STRUMENTI DI RICERCA</header><main><div class="eyebrow">Manoscritti digitalizzati</div><h1>Dalla Laurenziana a un unico PDF.</h1><p class="intro">Incolla il link di un manoscritto, seleziona la qualità e scarica tutte le riproduzioni in ordine. Nessuna installazione necessaria.</p>
<section class="panel"><label for="url">Indirizzo del manoscritto</label><input id="url" placeholder="https://tecabml.contentdm.oclc.org/digital/collection/plutei/id/146289/rec/1" value="https://tecabml.contentdm.oclc.org/digital/collection/plutei/id/146289/rec/1">
<p class="hint">Accetta link alle schede dei manoscritti della Biblioteca Medicea Laurenziana sulla piattaforma CONTENTdm.</p>
<div class="actions"><div class="select"><label for="quality">Qualità delle immagini</label><select id="quality"><option value="Originale">Originale</option><option value="Alta" selected>Alta</option><option value="Media">Media</option><option value="Bassa">Bassa</option></select></div><button class="primary" id="start" onclick="start()">Genera PDF →</button></div>
<div id="progressArea"><div id="status" class="status">Preparazione...</div><progress id="bar" max="100" value="0"></progress><p><button class="secondary" id="stop" onclick="stop()">Annulla download</button></p><a class="file" id="file">↓ Scarica il PDF</a></div>
</section><p class="foot">Puoi interrompere il lavoro con «Annulla download». Anche chiudendo la scheda, il server interromperà l'elaborazione dopo un breve periodo senza comunicazioni. Il PDF è temporaneo e viene eliminato automaticamente dopo circa un'ora. La disponibilità delle immagini dipende dal server della Laurenziana.</p></main>
<script>
let job=null,timer=null;
async function start(){
const btn=document.getElementById("start"),area=document.getElementById("progressArea"),status=document.getElementById("status");
btn.disabled=true;area.style.display="block";document.getElementById("file").style.display="none";document.getElementById("stop").style.display="inline-block";status.textContent="Avvio del download...";
try{let r=await fetch("/start",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({url:document.getElementById("url").value,quality:document.getElementById("quality").value})});let j=await r.json();if(!r.ok)throw Error(j.error);job=j.id;timer=setInterval(poll,1500);poll()}catch(e){status.textContent="Errore: "+e.message;btn.disabled=false}}
async function poll(){if(!job)return;try{let r=await fetch("/status/"+job);let j=await r.json();if(!r.ok)throw Error(j.error);
let p=j.total?Math.round(j.done/j.total*100):0;document.getElementById("bar").value=p;
document.getElementById("status").textContent=j.status==="starting"?"Ricerca del manoscritto...":j.status==="download"?`Download immagini: ${j.done} / ${j.total} (${p}%)`:j.status==="pdf"?"Creazione del PDF...":j.status==="ready"?"PDF pronto.":j.status==="cancelled"?"Download annullato.":j.status==="error"?"Errore: "+j.error:"Preparazione...";
if(["ready","error","cancelled"].includes(j.status)){clearInterval(timer);document.getElementById("start").disabled=false;document.getElementById("stop").style.display="none";if(j.status==="ready"){let a=document.getElementById("file");a.href="/file/"+job;a.style.display="inline-block";a.click()}job=null}
}catch(e){document.getElementById("status").textContent="Connessione interrotta: "+e.message;clearInterval(timer);document.getElementById("start").disabled=false}}
async function stop(){if(!job)return;clearInterval(timer);await fetch("/cancel/"+job,{method:"POST"});document.getElementById("status").textContent="Annullamento richiesto...";document.getElementById("start").disabled=false;document.getElementById("stop").style.display="none";job=null}
</script></body></html>"""

jobs={}
lock=threading.Lock()
TEMP=Path(tempfile.gettempdir())/"laurenziana_jobs"
TEMP.mkdir(exist_ok=True)
def worker(jid,url,quality):
    job=jobs[jid]
    try:
        j,_=manifest(url)
        pages=extract(j)
        if not pages:raise ValueError("Il manifest non contiene immagini.")
        job.update(total=len(pages),status="download")
        paths=[]
        for idx,(_,base,direct) in enumerate(pages):
            if job["cancel"].is_set():return
            img=download_image(base,direct,quality)
            p=TEMP/(jid+"_"+str(idx)+".jpg")
            img.save(p,"JPEG",quality=88,optimize=True)
            paths.append(p)
            job["done"]=idx+1
        if job["cancel"].is_set():return
        job["status"]="pdf"
        import img2pdf
        target=TEMP/(jid+".pdf")
        with open(target,"wb") as f:f.write(img2pdf.convert([str(p) for p in paths]))
        if job["cancel"].is_set():return
        job.update(status="ready",path=str(target),finished=time.time())
    except Exception as e:
        job.update(status="error",error=str(e),finished=time.time())
    finally:
        for p in TEMP.glob(jid+"_*.jpg"):
            try:p.unlink()
            except OSError:pass
        if job["cancel"].is_set():
            p=TEMP/(jid+".pdf")
            p.unlink(missing_ok=True)
            job["status"]="cancelled"
            job["finished"]=time.time()

@app.get("/")
def index():return render_template_string(HTML)

@app.post("/start")
def start():
    data=request.get_json(silent=True) or {}
    url=str(data.get("url",""))
    quality=data.get("quality","Alta")
    if quality not in ("Originale","Alta","Media","Bassa"):return jsonify(error="Qualità non valida"),400
    try:candidates(url)
    except Exception as e:return jsonify(error=str(e)),400
    with lock:
        active=sum(x["status"] in ("starting","download","pdf") for x in jobs.values())
        if active>=2:return jsonify(error="Il server è occupato. Riprova tra poco."),429
        jid=uuid.uuid4().hex
        jobs[jid]={"status":"starting","done":0,"total":0,"cancel":threading.Event(),"last_seen":time.time(),"created":time.time()}
    threading.Thread(target=worker,args=(jid,url,quality),daemon=True).start()
    return jsonify(id=jid)

@app.get("/status/<jid>")
def status(jid):
    job=jobs.get(jid)
    if not job:return jsonify(error="Download non trovato"),404
    job["last_seen"]=time.time()
    return jsonify(status=job["status"],done=job["done"],total=job["total"],error=job.get("error",""))

@app.post("/cancel/<jid>")
def cancel(jid):
    job=jobs.get(jid)
    if not job:return jsonify(error="Download non trovato"),404
    job["cancel"].set()
    return jsonify(ok=True)

@app.get("/file/<jid>")
def file(jid):
    job=jobs.get(jid)
    if not job or job["status"]!="ready":return jsonify(error="PDF non pronto"),404
    return send_file(job["path"],as_attachment=True,download_name="laurenziana_"+jid[:8]+".pdf",mimetype="application/pdf")

def cleanup():
    while True:
        time.sleep(30)
        now=time.time()
        for jid,job in list(jobs.items()):
            if job["status"] in ("starting","download","pdf") and now-job["last_seen"]>100:
                job["cancel"].set()
            if job["status"] in ("ready","error","cancelled") and now-job.get("finished",now)>3600:
                (TEMP/(jid+".pdf")).unlink(missing_ok=True)
                jobs.pop(jid,None)
threading.Thread(target=cleanup,daemon=True).start()
if __name__=="__main__":app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
