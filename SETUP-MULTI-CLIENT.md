# 🏗️ Setup Multi-Client Architecture

Esta guía te ayuda a configurar NOVA para trabajar con bases de datos de múltiples clientes.

---

## 📋 **Arquitectura**

```
┌─────────────────────────────────────────────────┐
│ RAILWAY PROJECT: nova-mvp                       │
├─────────────────────────────────────────────────┤
│                                                 │
│  [PostgreSQL 1] NOVA (ya existe)               │
│  └─ workflows, executions, chain_of_work       │
│  └─ client_credentials ← NUEVA TABLA            │
│                                                 │
│  [PostgreSQL 2] CLIENT-DB (crear ahora)        │
│  └─ invoices ← BD del cliente                  │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## 🚀 **PASO 1: Crear Segunda PostgreSQL en Railway**

1. **Ir a Railway Dashboard:**
   https://railway.com/project/c9b59f9a-d8ad-4545-86ba-e7e1028303bb

2. **Agregar nueva PostgreSQL:**
   - Click en **"New"** (botón azul arriba a la derecha)
   - Click en **"Database"**
   - Click en **"Add PostgreSQL"**
   - Railway la crea automáticamente

3. **Renombrar el servicio (opcional pero recomendado):**
   - Click en el nuevo servicio PostgreSQL
   - En la parte superior donde dice el nombre, cámbialo a: `client-db`
   - Esto te ayuda a distinguir cual es cual

4. **Copiar la DATABASE_URL:**
   - Dentro del servicio `client-db`
   - Tab **"Variables"**
   - Buscar la variable `DATABASE_URL`
   - Click en el icono de copiar (📋)
   - **Guardar en algún lado** (lo necesitaremos en el siguiente paso)

---

## 🔧 **PASO 2: Configurar Variables de Entorno**

Edita tu archivo `.env` local y agrega:

```bash
# NOVA Database (ya existe)
DATABASE_URL=postgresql://postgres:***@switchyard.proxy.rlwy.net:24821/railway

# Redis (ya existe)
REDIS_URL=redis://default:***@hopper.proxy.rlwy.net:13469

# E2B Sandbox (ya existe)
E2B_API_KEY=e2b_a58171ddb2be1e03333222f77fa4bd1273e6f699

# ✨ NUEVA: Client Database (pegar la URL que copiaste de Railway)
CLIENT_DB_URL=postgresql://postgres:***@[NUEVO_HOST]:[PUERTO]/railway

# ✨ NUEVA: Gmail credentials (configuraremos después)
GMAIL_USER=tu_email@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
SENDER_WHITELIST=remitente@empresa.com
```

**IMPORTANTE**: Reemplaza `CLIENT_DB_URL` con la URL que copiaste en el Paso 1.

---

## 📦 **PASO 3: Ejecutar Script de Setup**

Este script automáticamente:
- ✅ Ejecuta migración de Alembic (crea tabla `client_credentials`)
- ✅ Inserta credenciales del cliente de prueba
- ✅ Crea tabla `invoices` en la BD del cliente
- ✅ Verifica que todo funciona

```bash
cd /Users/marioferrer/automatizaciones/nova
python scripts/setup_multi_client.py
```

**Output esperado:**
```
============================================================
NOVA Multi-Client Setup
============================================================

📊 NOVA Database: postgresql://postgres...
📊 Client Database: postgresql://postgres...

🔧 Running Alembic migration...
✅ Migration complete

📝 Inserting test client credentials...
✅ Test client configured: test-client
   DB: [host]:[port]/railway

🔌 Verifying connection to client database...
✅ Connected successfully!
   PostgreSQL version: PostgreSQL 16.x...

🗄️  Creating invoices table in client database...
✅ Invoices table created successfully

🧪 Testing get_client_db_connection()...
✅ Helper function works! Invoices table has 0 rows

============================================================
✅ Multi-Client Setup Complete!
============================================================
```

---

## ✅ **PASO 4: Verificar en Railway**

### **Verificar NOVA DB (tiene nueva tabla)**

1. Ir a Railway → servicio PostgreSQL original (no el nuevo)
2. Tab **"Data"**
3. Debería aparecer nueva tabla: `client_credentials`
4. Click en la tabla
5. Debería tener 1 fila con el test-client

### **Verificar Client DB (tiene tabla invoices)**

1. Ir a Railway → servicio `client-db` (el nuevo)
2. Tab **"Data"**
3. Debería aparecer tabla: `invoices`
4. Click en la tabla
5. Debería estar vacía (0 filas)

---

## 🧪 **PASO 5: Test Manual (Opcional)**

Para verificar que la función `get_client_db_connection()` funciona:

```python
# En Python interactive o script de prueba
from src.models.client_credentials import get_client_db_connection

# Conectar a BD del cliente
conn = get_client_db_connection("test-client")
cursor = conn.cursor()

# Insertar una factura de prueba
cursor.execute("""
    INSERT INTO invoices (email_from, total_amount, currency)
    VALUES (%s, %s, %s)
    RETURNING id;
""", ("test@example.com", 850.00, "EUR"))

invoice_id = cursor.fetchone()[0]
print(f"✅ Invoice inserted with ID: {invoice_id}")

conn.commit()
cursor.close()
conn.close()
```

---

## 📝 **Siguiente Paso**

Ahora que tienes la arquitectura multi-cliente configurada, el siguiente paso es:

**Crear el Workflow de Facturas:**
- JSON con 9 nodos (StartNode, ActionNodes, DecisionNodes, EndNode)
- Código Python para cada ActionNode
- Script de prueba end-to-end

¿Listo para crear el workflow? 🚀

---

## 🆘 **Troubleshooting**

### Error: "DATABASE_URL not set"
- Verifica que tu `.env` tiene `DATABASE_URL` configurado
- Ejecuta: `source .env` o reinicia tu terminal

### Error: "CLIENT_DB_URL not set"
- Verifica que copiaste bien la URL del paso 1
- Debe empezar con `postgresql://`

### Error: "Connection refused"
- Verifica que Railway no tiene downtime
- Verifica que la URL incluye el puerto correcto

### Error: "Client 'test-client' not found"
- Ejecuta: `python scripts/setup_multi_client.py` de nuevo
- Verifica que la tabla `client_credentials` existe en NOVA DB

---

## 💡 **Agregar Más Clientes en el Futuro**

Para agregar un segundo cliente (ej: "acme"):

```sql
-- Ejecutar en NOVA Database
INSERT INTO client_credentials (
    client_name, client_slug,
    db_host, db_port, db_name, db_user, db_password,
    is_active, created_at, updated_at
) VALUES (
    'ACME Corp', 'acme',
    'acme-db.example.com', 5432, 'acme_production', 'acme_user', 'secret',
    true, NOW(), NOW()
);
```

Luego en el workflow:
```python
# context["client_slug"] = "acme"
conn = get_client_db_connection(context["client_slug"])
```

---

¿Preguntas? Revisa la arquitectura en `/documentacion/ARQUITECTURA.md`
