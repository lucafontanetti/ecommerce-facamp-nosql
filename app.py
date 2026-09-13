import os, uuid
from datetime import datetime, timezone
from functools import wraps
import requests
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

app=Flask(__name__)
app.secret_key=os.getenv("SECRET_KEY","dev-change-me")
COUCHDB_URL=os.getenv("COUCHDB_URL","http://admin:admin@127.0.0.1:5984").rstrip("/")
DB_NAME=os.getenv("COUCHDB_DATABASE","ecommerce_facamp")
DB_URL=f"{COUCHDB_URL}/{DB_NAME}"

def raw(method,url,**kw):
    r=requests.request(method,url,timeout=10,**kw)
    if r.status_code>=400: raise RuntimeError(f"CouchDB {r.status_code}: {r.text}")
    return r.json() if r.text else {}

def couch(method,path="",**kw): return raw(method,f"{DB_URL}{path}",**kw)

def ensure_db():
    r=requests.put(DB_URL,timeout=10)
    if r.status_code not in (201,202,412): raise RuntimeError(r.text)

def save(doc):
    return couch("PUT",f"/{doc['_id']}",json=doc) if '_id' in doc else couch("POST","",json=doc)

def get(doc_id): return couch("GET",f"/{doc_id}")

def find(selector,fields=None,limit=100):
    p={"selector":selector,"limit":limit}
    if fields:p["fields"]=fields
    return couch("POST","/_find",json=p).get("docs",[])

def seed():
    ensure_db()
    docs=[
      {"_id":"produto:teclado","tipo":"produto","nome":"Teclado Mecânico","categoria":"Tecnologia","preco":299.90,"estoque":20,"ativo":True},
      {"_id":"produto:mouse","tipo":"produto","nome":"Mouse Sem Fio","categoria":"Tecnologia","preco":159.90,"estoque":35,"ativo":True},
      {"_id":"produto:mochila","tipo":"produto","nome":"Mochila Executiva","categoria":"Acessórios","preco":189.90,"estoque":12,"ativo":True}]
    for d in docs:
        r=requests.put(f"{DB_URL}/{d['_id']}",json=d,timeout=10)
        if r.status_code not in (201,202,409): raise RuntimeError(r.text)
    for fields,name in [(["tipo","ativo"],"idx_tipo_ativo"),(["tipo","email"],"idx_tipo_email"),(["tipo","cliente_id"],"idx_tipo_cliente"),(["tipo","categoria"],"idx_tipo_categoria")]:
        couch("POST","/_index",json={"index":{"fields":fields},"name":name,"type":"json"})

def login_required(fn):
    @wraps(fn)
    def wrap(*a,**k):
        if not session.get('cliente_id'):
            flash('Faça login para continuar.'); return redirect(url_for('login'))
        return fn(*a,**k)
    return wrap

@app.route('/')
def catalogo():
    ps=find({"tipo":"produto","ativo":True},["_id","nome","categoria","preco","estoque","ativo"]); ps.sort(key=lambda x:x['nome'])
    return render_template('catalogo.html',produtos=ps)

@app.post('/carrinho/adicionar/<path:produto_id>')
def adicionar(produto_id):
    p=get(produto_id); cart=session.get('carrinho',{}); qtd=int(cart.get(produto_id,0))+1
    if qtd>int(p.get('estoque',0)): flash('Estoque insuficiente.'); return redirect(url_for('catalogo'))
    cart[produto_id]=qtd; session['carrinho']=cart; session.modified=True; return redirect(url_for('catalogo'))

@app.route('/carrinho')
def carrinho():
    itens=[]; total=0.0
    for pid,qtd in session.get('carrinho',{}).items():
        p=get(pid); sub=float(p['preco'])*int(qtd); total+=sub; itens.append({'produto':p,'qtd':int(qtd),'subtotal':sub})
    return render_template('carrinho.html',itens=itens,total=total)

@app.route('/cadastro',methods=['GET','POST'])
def cadastro():
    if request.method=='POST':
        email=request.form['email'].strip().lower()
        if find({"tipo":"cliente","email":email},limit=1): flash('E-mail já cadastrado.'); return render_template('cadastro.html')
        d={"_id":f"cliente:{uuid.uuid4()}","tipo":"cliente","nome":request.form['nome'].strip(),"email":email,"senha_hash":generate_password_hash(request.form['senha']),"criado_em":datetime.now(timezone.utc).isoformat()}
        save(d); flash('Cadastro realizado.'); return redirect(url_for('login'))
    return render_template('cadastro.html')

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        cs=find({"tipo":"cliente","email":request.form['email'].strip().lower()},limit=1)
        if not cs or not check_password_hash(cs[0]['senha_hash'],request.form['senha']): flash('Credenciais inválidas.'); return render_template('login.html')
        session['cliente_id']=cs[0]['_id']; session['cliente_nome']=cs[0]['nome']; return redirect(url_for('catalogo'))
    return render_template('login.html')

@app.get('/logout')
def logout(): session.clear(); return redirect(url_for('catalogo'))

@app.post('/checkout')
@login_required
def checkout():
    cart=session.get('carrinho',{})
    if not cart: flash('Carrinho vazio.'); return redirect(url_for('catalogo'))
    updates=[]; itens=[]; total=0.0
    for pid,qtd in cart.items():
        p=get(pid); qtd=int(qtd)
        if p['estoque']<qtd: flash(f"Estoque insuficiente para {p['nome']}"); return redirect(url_for('carrinho'))
        itens.append({"produto_id":p['_id'],"nome":p['nome'],"quantidade":qtd,"preco_unitario":float(p['preco'])}); total+=qtd*float(p['preco']); p['estoque']-=qtd; updates.append(p)
    pedido={"_id":f"pedido:{uuid.uuid4()}","tipo":"pedido","cliente_id":session['cliente_id'],"status":"CRIADO","itens":itens,"total":round(total,2),"criado_em":datetime.now(timezone.utc).isoformat()}
    result=couch("POST","/_bulk_docs",json={"docs":updates+[pedido]})
    if any(x.get('error') for x in result): flash('Conflito no checkout; recarregue e tente novamente.'); return redirect(url_for('carrinho'))
    session['carrinho']={}; flash('Pedido criado.'); return redirect(url_for('pedidos'))

@app.get('/pedidos')
@login_required
def pedidos():
    ps=find({"tipo":"pedido","cliente_id":session['cliente_id']}); ps.sort(key=lambda x:x.get('criado_em',''),reverse=True)
    return render_template('pedidos.html',pedidos=ps)

@app.cli.command('init-db')
def init_db(): seed(); print('Banco CouchDB inicializado.')

if __name__=='__main__': ensure_db(); app.run(debug=True)
