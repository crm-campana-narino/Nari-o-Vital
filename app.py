from flask import Flask, render_template, request, redirect, url_for, flash, Response, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import csv
import io

app = Flask(__name__)
app.config['SECRET_KEY'] = 'clave_secreta_campana_narino'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///campana_central.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {"pool_pre_ping": True}

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

def limpiar_coordenada(valor):
    if not valor: return None
    try: return float(str(valor).replace(',', '').strip())
    except ValueError: return None

class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuario'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    es_admin = db.Column(db.Boolean, default=False)

class Contacto(db.Model):
    __tablename__ = 'contacto'
    id = db.Column(db.Integer, primary_key=True)
    campana = db.Column(db.String(100))
    cedula = db.Column(db.String(20))
    nombre = db.Column(db.String(100))
    telefono = db.Column(db.String(20))
    municipio = db.Column(db.String(100))
    subregion = db.Column(db.String(100))
    barrio_vereda = db.Column(db.String(100))
    latitud = db.Column(db.Float, nullable=True)
    longitud = db.Column(db.Float, nullable=True)
    tipo = db.Column(db.String(50)) 
    otro_tipo = db.Column(db.String(100))
    compromiso = db.Column(db.Integer, default=1)
    creador_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    creador = db.relationship('Usuario', backref='contactos')

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username_input = request.form.get('username').strip()
        user = Usuario.query.filter_by(username=username_input).first()
        if user and check_password_hash(user.password_hash, request.form.get('password')):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Usuario o contraseña incorrectos')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    if current_user.es_admin:
        try:
            todos_contactos = Contacto.query.all()
            total_contactos = len(todos_contactos)
            total_lideres = sum(1 for c in todos_contactos if c.tipo in ['Lider Campaña', 'Lider Comunal'])
            total_electores = sum(1 for c in todos_contactos if c.tipo == 'Elector')
            
            conteo_lideres = {}
            for c in todos_contactos:
                nombre_lider = c.creador.username if c.creador else "Desconocido"
                conteo_lideres[nombre_lider] = conteo_lideres.get(nombre_lider, 0) + 1
                
            return render_template('admin_dashboard.html', contactos=todos_contactos, total=total_contactos, lideres=total_lideres, electores=total_electores, conteo_lideres=conteo_lideres)
        except Exception as e:
            return f"Error en el Panel de Admin: {str(e)}", 500
    else:
        try:
            mis_contactos = Contacto.query.filter_by(creador_id=current_user.id).all()
            return render_template('dashboard.html', contactos=mis_contactos)
        except Exception as e:
            return f"Error en el Panel del Líder: {str(e)}", 500

@app.route('/mapa')
@login_required
def mapa():
    if not current_user.es_admin: return "Acceso denegado", 403
    return render_template('mapa.html')

@app.route('/datos_mapa')
@login_required
def datos_mapa():
    if not current_user.es_admin: return jsonify([])
    contactos = Contacto.query.filter(Contacto.latitud.isnot(None)).all()
    datos = [{"nombre": c.nombre, "lat": c.latitud, "lon": c.longitud, "tipo": c.tipo} for c in contactos]
    return jsonify(datos)

@app.route('/crear_lider', methods=['POST'])
@login_required
def crear_lider():
    if not current_user.es_admin: return "Acceso denegado", 403
    
    nuevo_usuario = request.form.get('nuevo_usuario').strip()
    nueva_clave = request.form.get('nueva_clave').strip()
    
    if Usuario.query.filter_by(username=nuevo_usuario).first():
        flash(f'El usuario {nuevo_usuario} ya existe.')
    else:
        try:
            user = Usuario(username=nuevo_usuario, password_hash=generate_password_hash(nueva_clave), es_admin=False)
            db.session.add(user)
            db.session.commit()
            flash(f'Líder {nuevo_usuario} creado exitosamente.')
        except Exception as e:
            db.session.rollback()
            # Si hay un error, lo mostramos en pantalla en lugar de romper la App
            return f"Error al crear líder (Revisa si usaste espacios): {str(e)}", 500
    return redirect(url_for('dashboard'))

@app.route('/eliminar_contacto/<int:id>')
@login_required
def eliminar_contacto(id):
    if not current_user.es_admin: return "Acceso denegado", 403
    try:
        contacto = Contacto.query.get_or_404(id)
        db.session.delete(contacto)
        db.session.commit()
        flash('Contacto eliminado.')
    except Exception as e:
        return f"Error al eliminar: {str(e)}", 500
    return redirect(url_for('dashboard'))

@app.route('/editar_contacto/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_contacto(id):
    if not current_user.es_admin: return "Acceso denegado", 403
    try:
        contacto = Contacto.query.get_or_404(id)
        if request.method == 'POST':
            contacto.cedula = request.form.get('cedula')
            contacto.nombre = request.form.get('nombre')
            contacto.telefono = request.form.get('telefono')
            contacto.municipio = request.form.get('municipio')
            contacto.barrio_vereda = request.form.get('barrio_vereda')
            contacto.tipo = request.form.get('tipo')
            contacto.compromiso = int(request.form.get('compromiso'))
            db.session.commit()
            flash('Contacto actualizado.')
            return redirect(url_for('dashboard'))
        return render_template('editar_contacto.html', contacto=contacto)
    except Exception as e:
        return f"Error al editar: {str(e)}", 500

@app.route('/registrar', methods=['POST'])
@login_required
def registrar():
    try:
        nuevo_contacto = Contacto(
            campana=request.form.get('campana'), cedula=request.form.get('cedula'), nombre=request.form.get('nombre'),
            telefono=request.form.get('telefono'), municipio=request.form.get('municipio'), subregion=request.form.get('subregion'),
            barrio_vereda=request.form.get('barrio'), tipo=request.form.get('tipo'),
            otro_tipo=request.form.get('otro_tipo') if request.form.get('tipo') == 'Otro' else None,
            compromiso=int(request.form.get('compromiso')), latitud=limpiar_coordenada(request.form.get('latitud')), 
            longitud=limpiar_coordenada(request.form.get('longitud')), creador_id=current_user.id
        )
        db.session.add(nuevo_contacto)
        db.session.commit()
        flash('Contacto registrado exitosamente')
    except Exception as e:
        db.session.rollback()
        return f"Error al registrar el contacto: {str(e)}", 500
    return redirect(url_for('dashboard'))

@app.route('/exportar')
@login_required
def exportar():
    if not current_user.es_admin: return "Acceso denegado", 403
    contactos = Contacto.query.all()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Campaña', 'Cédula', 'Nombre', 'Teléfono', 'Municipio', 'Subregión', 'Barrio', 'Tipo', 'Otro Tipo', 'Compromiso', 'Latitud', 'Longitud', 'Registrado por'])
    for c in contactos:
        writer.writerow([c.campana, c.cedula, c.nombre, c.telefono, c.municipio, c.subregion, c.barrio_vereda, c.tipo, c.otro_tipo, c.compromiso, c.latitud, c.longitud, c.creador.username if c.creador else "Admin"])
    response = Response(output.getvalue(), mimetype='text/csv')
    response.headers["Content-Disposition"] = "attachment; filename=Base_Datos_Campana.csv"
    return response

if __name__ == '__main__':
    app.run(debug=True)
