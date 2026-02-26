---

# 🧩 **ONBOARDING – PROYECTO IA GRUPO NAGAKI**

### *Implementación de Asistente de Voz + Agente Multicanal + Automatizaciones con n8n + Integración CRM*

---

# I. **Description**

---

↓ Descripción clara del proyecto, visión, objetivos y principios.

**Grupo Nagaki – Proyecto de Automatización e Inteligencia Artificial**

El objetivo principal es **sustituir la carga operativa**, filtrar correctamente a los clientes y **automatizar toda la atención inicial**, tanto por teléfono como por WhatsApp, garantizando un trato profesional, humano y especializado en subastas, cesión de remate y venta de crédito hipotecario.

Volumen aproximado: 10-20 llamadas al dia, 20-50 clientes al dia.

### **Desarrollo técnico incluido:**

- Agente de voz 24/7 en español e inglés (modelo: *Laura*)
- Chatbot 24/7 Respuesta automatizada de WhatsApp (entrante + seguimiento)
- Gestión de llamadas de Madrid y Barcelona con ramificación automática
- Integración con CRM actual (Idealista/portales + CRM interno vía scraping export → base interna)
- Base de datos estructurada: leads, llamadas, intención, filtros, estado, summary
- Memoria a largo plazo del cliente (vector DB)
- Notificaciones automáticas al equipo (WhatsApp, email)
- Flujo de clasificación de leads: **interesados reales** vs **curiosos / no cualificados**
- Transferencia a humano cuando el cliente está listo para visita o tiene casuística compleja
- Automatización de envíos de mapas, fotos, contexto del piso, guiones legales
- Mini seguimiento.

---

# II. **PERFIL GENERAL DEL NEGOCIO**

---

## 📍 **Identidad de Grupo Nagaki**

- **Nombre:** Grupo Nagaki 2010 S.L.
- **Ubicación:** Barcelona y Madrid
- **Año de fundación:** +10 años
- **Especialización:** Venta de activos inmobiliarios complejos
- **Equipo clave:**
    - Javier (Barcelona, fundador)
    - Javier (Madrid, responsable de gestión y llamadas)
    - Jesús (colaborador comercial Madrid)
    - Equipo externo de centralita (actual)

---

# 🏢 **OPERATIVA DEL NEGOCIO**

| Área | Detalle |
| --- | --- |
| **Tipología de activos** | Subastas, cesión de remate, ventas de crédito, ocupados, deuda hipotecaria |
| **Zonas** | Principal: Barcelona y Madrid. Adicional: Toledo, Ávila, Segovia, Málaga, Almería, Valencia |
| **Canales actuales** | Idealista, Fotocasa, Habitaclia, CRM interno conectado a portales |
| **Gestión actual** | 90% vía Idealista/Fotocasa (mensajes, llamadas, emails) |
| **Volumen** | +90 inmuebles actuales, proyectando crecimiento a 500–1000 |
| **Problema crítico** | Llamadas masivas por precio barato → 80% curiosos → alto desgaste → pérdida de tiempo |
| **Disponibilidad** | Nocturnos y fines de semana llegan llamadas perdidas |
| **Duración típica de llamada manual** | 20–30 minutos explicando conceptos complejos |
| **Riesgo** | Si Javier no contesta → no hay gestión; si se pone malo → negocio se detiene |

---

# 🔑 **NATURALEZA DEL PRODUCTO (esencial para el agente de IA)**

La mayoría de usuarios **no entiende lo que ve en Idealista**, incluso si lo pone en el anuncio.

El agente debe dominar 4 conceptos clave con sus casuísticas:

### **1. Cesión de remate**

- Compra tras subasta judicial
- No visitable
- No hipotecable
- Requiere capital propio

### **2. Venta de crédito hipotecario (NPL)**

- Se compra la deuda, no la vivienda
- Puede tardar 6–24 meses en adjudicarse
- Alto componente legal
- Necesita explicación clara y sencilla

### **3. Ocupados**

- Vivienda sin posesión
- Baja visitabilidad
- Precio atractivo
- Alta incertidumbre para particulares

### **4. Venta tradicional (con llaves)**

- Visitables
- Se prioriza agendar visita si cliente cualifica
- IA debe enviar dirección/mapa por WhatsApp

---

# 💰 **PLANES Y ORIENTACIÓN A INVERSORES**

| Tipo de cliente | Cómo debe gestionarlo la IA |
| --- | --- |
| **Inversores profesionales** | Son prioritarios. Se les filtra rápido y se les pasa a humano. |
| **Particulares en fase de curiosidad** | Explicar con calma, educar, filtrar y detectar si CUALIFICA. |
| **Curiosos sin dinero** | Filtrado duro → no perder tiempo. |
| **Inversores que piden “chollos”** | Explicar que todos son chollos, pero cada uno con riesgo. |

---

# 📞 **FUNCIONES CLAVE DEL AGENTE DE VOZ**

El agente debe actuar como **asistente inmobiliario especializado de Grupo Nagaki**, capaz de:

### ✔ Filtrar llamadas:

- ¿Tiene dinero disponible?
- ¿Busca inversión a medio plazo?
- ¿O sólo está curioseando por precio?

### ✔ Detectar intención:

- Comprar
- Visitar
- Conocer más sobre remate/crédito
- Saber si es posible ver el inmueble
- Pedir ubicación
- Pedir fotos
- Dudas legales

### ✔ Explicar con claridad:

- Cesión de remate
- Venta de crédito hipotecario
- Plazos
- Riesgos
- Por qué no se pueden ver algunos pisos
- Por qué están baratos

### ✔ Hacer seguimiento

WhatsApp automatizado, email, recordatorios.

### ✔ Transferir a humano

Cuando el lead es **calificado**:

- Tiene el dinero
- Entiende el proceso
- Acepta que no se puede hipotecar
- Está dispuesto a firmar contrato de cesión
- Quiere visita física
- Quiere reservar piso

### ✔ Registrar todo en la base de datos

Nombre, teléfono, inmueble, intención, cualificación, summary.

---

# 🎙️ **PERSONALIDAD DEL AGENTE**

| Rasgo | Descripción |
| --- | --- |
| **Tono:** | Profesional, claro, seguro, humano. |
| **Actitud:** | Paciente, explicativa, resolutiva. |
| **Lenguaje:** | Español neutro; inglés opcional. Catalán no obligatorio. |
| **Rol percibido:** | *“Asistente inmobiliario de Grupo Nagaki”*. |
| **Duración recomendada:** | 2–5 minutos máximo. |
| **Educación financiera** | Debe enseñarle al cliente cómo funciona el producto. |

---

# 🔁 **FLUJO IDEAL DE LLAMADA (Estructura)**

### **1. Saludo inicial**

> “Hola, gracias por llamar a Grupo Nagaki.
> 
> 
> Soy Laura, asistente del equipo inmobiliario.
> 
> ¿Cómo puedo ayudarte?”
> 

---

### **2. Clasificación inmediata**

> “¿Llamas por un inmueble que has visto en Idealista/Habitaclia?
> 
> 
> ¿Recuerdas la zona o referencia?”
> 

---

### **3. Filtrado crítico**

La IA debe preguntar:

- ¿Tiene el dinero disponible?
- ¿Conoce la figura de *cesión de remate* o *venta de crédito*?
- ¿Busca inversión o vivienda propia?
- ¿Le interesa un proceso de 6–24 meses?
- ¿Es imprescindible visitar la vivienda?

---

### **4. Explicación personalizada según el caso**

La IA debe adaptar el guion según la casuística:

- Ocupado
- No hipotecable
- Venta de deuda
- Cesión de remate
- Adjudicación pendiente
- Llaves disponibles
- Zona concreta

---

### **5. Acción final (una de estas 3)**

1. **Lead cualificado → Transferir a Javier o comercial**
2. **Lead interesado pero no cualificado → seguimiento por WhatsApp**
3. **Lead curioso sin intención → educar y cerrar cortésmente**

---

### **6. Despedida**

> “Te enviaré ahora mismo la información por WhatsApp y un resumen.
> 
> 
> Gracias por contactar a Grupo Nagaki.”
> 

---

# 📲 **FUNCIONES TÉCNICAS DEL AGENTE**

| Función | Acción |
| --- | --- |
| WhatsApp | Enviar info, fotos, enlaces, ubicación, resumen, requisitos |
| CRM | Registrar datos + tipología + interés + nivel de cualificación |
| Integración web | Capturar leads de formularios |
| Detección de spam | Bloqueo automático |
| Números Barcelona/Madrid | Clasificación automática |
| Notificación al equipo | Lead cualificado → enviar al comercial correcto |
| Memoria | Recordar conversaciones previas, intención y progreso |

---

# 🧠 **PALABRAS CLAVE QUE LA IA DEBE RECONOCER**

- "Remate"
- "Subasta"
- "Crédito hipotecario"
- "Ocupado"
- "Puedo visitar"
- "Hipotecable"
- "Inversión"
- "Tengo el dinero"
- "No entiendo cómo funciona"
- "Quiero fotos"
- "Mándame ubicación"
- "Precio"
- "Estoy interesado"
- "Chollos"
- "Referencias"

---

# 🎧 **PROMPT BASE (Voz / WhatsApp / Multicanal)**

> “Eres Laura, asistente inmobiliaria especializada de Grupo Nagaki.
> 
> 
> Tu función es **filtrar clientes**, **explicar conceptos complejos**, **detectar intención**, **educar**, **cualificar** y **transferir sólo cuando el cliente realmente está listo**.
> 
> Habla siempre con seguridad, claridad y empatía.
> 
> Tu prioridad es **ahorrar tiempo**, **resolver rápido**, y **no permitir conversaciones largas con curiosos que no tienen intención real**.
> 
> Adapta tu explicación según el tipo de activo: remate, crédito, subasta u ocupado.
> 
> Si el cliente cualifica → transfiere.
> 
> Si no cualifica → educa brevemente y corta con elegancia.
> 
> Registra absolutamente todo en la base de datos.”
> 

---

# III. **NEXT STEPS – Sesión de Onboarding**

Durante la sesión se deberá recopilar:

### ✔ Información técnica

- Acceso al CRM o confirmación de scraping
- Acceso a webforms
- Números telefónicos de Barcelona/Madrid
- Emails oficiales
- Preferencias de notificaciones (WhatsApp / email)
- Integraciones deseadas

### ✔ Información operativa

- Guiones oficiales
- Ejemplos reales de conversaciones
- Requisitos legales (datos, disclaimers, procesos)
- Límites de actuación de la IA
- Mapas, fotos, documentación típica

### ✔ Información de negocio

- Qué es lead cualificado para ellos
- Cómo se hacen visitas
- Qué pisos pueden visitarse
- Qué pisos no
- Cómo se explican los procesos complejos
- Política de transferencia
- Disclaimers legales (uso del archivo *Politicas.pdf*)

---

# IV. **ENTREGABLES**

1. Agente de voz operativo 24/7
2. Agente WhatsApp + Email + Webforms
3. Base de datos centralizada
4. Flujos n8n para:
    - Clasificación
    - Notificaciones
    - Seguimiento
5. Integración con CRM / scraping inicial
6. Guía de uso para el cliente
7. Optimización semanal durante fase beta