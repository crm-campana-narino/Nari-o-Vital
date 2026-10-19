from flask import Flask, render_template, request, redirect, url_for, flash, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import csv
import io

app = Flask(__name__)
app.config['SECRET_KEY'] = 'clave_secreta_campana_narino'

# CONFIGURACIÓN DE LA BASE DE DATOS Y EL POOL DE CONEXIONES
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///campana_central.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
    'pool_size': 5,
    'max_overflow': 2
}

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ============================================================================
# MODELOS
# ============================================================================
class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    es_admin = db.Column(db.Boolean, default=False)

class Contacto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    campana = db.Column(db.String(100), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(20))
    municipio = db.Column(db.String(100), nullable=False)
    subregion = db.Column(db.String(100), nullable=False)
    barrio_vereda = db.Column(db.String(100), nullable=False)
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

# ============================================================================
# RUTAS
# ============================================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = Usuario.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
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
        todos_contactos = Contacto.query.all()
        
        total_contactos = len(todos_contactos)
        total_lideres = sum(1 for c in todos_contactos if c.tipo in ['Lider Campaña', 'Lider Comunal'])
        total_electores = sum(1 for c in todos_contactos if c.tipo == 'Elector')
        
        conteo_lideres = {}
        for c in todos_contactos:
            nombre_lider = c.creador.username if c.creador else "Desconocido"
            conteo_lideres[nombre_lider] = conteo_lideres.get(nombre_lider, 0) + 1
            
        return render_template('admin_dashboard.html', 
                               contactos=todos_contactos, 
                               total=total_contactos, 
                               lideres=total_lideres, 
                               electores=total_electores,
                               conteo_lideres=conteo_lideres)
    else:
        mis_contactos = Contacto.query.filter_by(creador_id=current_user.id).all()
        return render_template('dashboard.html', contactos=mis_contactos)

@app.route('/registrar', methods=['POST'])
@login_required
def registrar():
    campana = request.form.get('campana')
    nombre = request.form.get('nombre')
    telefono = request.form.get('telefono')
    municipio = request.form.get('municipio')
    subregion = request.form.get('subregion')
    barrio = request.form.get('barrio')
    tipo = request.form.get('tipo')
    otro_tipo = request.form.get('otro_tipo') if tipo == 'Otro' else None
    compromiso = request.form.get('compromiso')
    lat = request.form.get('latitud')
    lon = request.form.get('longitud')

    nuevo_contacto = Contacto(
        campana=campana, nombre=nombre, telefono=telefono, 
        municipio=municipio, subregion=subregion, barrio_vereda=barrio, 
        tipo=tipo, otro_tipo=otro_tipo, compromiso=int(compromiso), 
        latitud=float(lat) if lat else None, longitud=float(lon) if lon else None,
        creador_id=current_user.id
    )
    db.session.add(nuevo_contacto)
    db.session.commit()
    flash('Contacto registrado exitosamente')
    return redirect(url_for('dashboard'))

@app.route('/exportar')
@login_required
def exportar():
    if not current_user.es_admin:
        return "Acceso denegado", 403
        
    contactos = Contacto.query.all()
    
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    
    writer.writerow(['Campaña', 'Nombre', 'Teléfono', 'Municipio', 'Subregión', 'Barrio', 'Tipo', 'Otro Tipo', 'Compromiso', 'Latitud', 'Longitud', 'Registrado por'])
    
    for c in contactos:
        writer.writerow([
            c.campana, c.nombre, c.telefono, c.municipio, c.subregion, 
            c.barrio_vereda, c.tipo, c.otro_tipo, c.compromiso, 
            c.latitud, c.longitud, c.creador.username if c.creador else "Admin"
        ])
    
    response = Response(output.getvalue(), mimetype='text/csv')
    response.headers["Content-Disposition"] = "attachment; filename=Base_Datos_Campana.csv"
    return response

# ============================================================================
# INICIALIZACIÓN
# ============================================================================
def init_db():
    with app.app_context():
        db.create_all()
        if not Usuario.query.filter_by(username='admin').first():
            admin = Usuario(username='admin', password_hash=generate_password_hash('admin123'), es_admin=True)
            db.session.add(admin)
            lider = Usuario(username='lider1', password_hash=generate_password_hash('lider123'), es_admin=False)
            db.session.add(lider)
            db.session.commit()
            print("Base de datos creada. Admin: admin / admin123 | Lider: lider1 / lider123")

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
