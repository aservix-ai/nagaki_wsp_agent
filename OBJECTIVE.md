# Contexto del Proyecto: Asistente IA Grupo Nagaki ("Laura")

## 1. Visión General
El objetivo de este proyecto es desarrollar un ecosistema de automatización e Inteligencia Artificial para **Grupo Nagaki**, una empresa inmobiliaria especializada en activos complejos (subastas, cesiones de remate, venta de crédito hipotecario y pisos ocupados).

El sistema debe sustituir la carga operativa de atención inicial, filtrar "curiosos" y educar a los clientes sobre productos de inversión complejos, garantizando que los agentes humanos solo interactúen con leads cualificados (inversores con capital propio).

## 2. Objetivos Principales del Agente
1.  **Filtrado Agresivo pero Educado:** Diferenciar entre "inversores reales" (con dinero al contado) y "curiosos" (buscan hipotecas en activos no financiables).
2.  **Educación Financiera:** Explicar conceptos complejos (Cesión de Remate, NPL, Ocupados) de forma sencilla, aclarando riesgos y plazos (6-24 meses).
3.  **Atención Omnicanal 24/7:** Gestión de Voz (llamadas entrantes/salientes) y WhatsApp automatizado.
4.  **Gestión de Datos:** Registro estructurado en Base de Datos y sincronización con CRMs.

## 3. Perfil del Agente ("Laura")
* **Rol:** Asistente inmobiliario de Grupo Nagaki.
* **Tono:** Profesional, segura, empática y resolutiva.
* **Idioma:** Español neutro (prioridad), Inglés (si el cliente lo requiere), Catalán (derivación o cambio a castellano).
* **Regla de Oro:** No permitir conversaciones largas con curiosos sin intención/capacidad de compra.

## 4. Funcionalidades Técnicas (Scope)
### A. Agente de Voz
* Debe manejar interrupciones y latencia baja.
* Capaz de clasificar llamadas según origen (Madrid vs Barcelona).
* **Transferencia:** SOLO transfiere a humanos si es una **emergencia** real.

### B. Automatización WhatsApp & Email
* Envío de fichas, fotos (si existen), ubicaciones (parciales) y resúmenes de llamadas.
* Seguimiento automático a leads interesados pero no cerrados.

### C. Integraciones y Datos
* **Base de Datos:** PostgreSQL/Supabase (Leads, Llamadas, Intención, Summary, Vector Store para memoria a largo plazo).
* **Orquestación:** n8n para flujos de trabajo (notificaciones, clasificación).
* **CRMs:**
    * Madrid: Integración/Scraping con **Idealista**.
    * Barcelona: Integración con **InmoPC**.

## 5. Lógica de Negocio y Reglas Críticas
### Criterios de Cualificación (El "Happy Path")
Para considerar un lead cualificado, el agente debe validar:
1.  **Capacidad Económica:** ¿Tiene el dinero disponible al contado? (No hipoteca para activos judiciales).
2.  **Entendimiento:** ¿Comprende que no se puede visitar y los plazos judiciales?
3.  **Intención:** Inversión vs Vivienda habitual.

### Manejo de Objeciones y "Red Flags"
* **Pide visitar piso NO visitable:** Explicar que es un proceso judicial/ocupado. No dar falsas esperanzas.
* **Pide dirección exacta:** Dar calle y número, NUNCA piso y puerta.
* **Quiere hipoteca en Cesión de Remate:** Explicar que no es posible. Ofrecer producto "Libre" o descalificar educadamente.

## 6. Definición de Productos (Knowledge Base)
El agente debe dominar las diferencias entre:
* **Cesión de Remate:** Compra tras subasta, requiere capital propio, no visitable, no hipotecable.
* **Venta de Crédito (NPL):** Compra de deuda, no del inmueble directo. Alto componente legal.
* **Ocupados:** Precio atractivo, alta incertidumbre, no visitable.
* **Venta Tradicional:** Visitables, con llaves, hipotecables (prioridad agendar visita).

## 7. Flujos de Trabajo
1.  **Entrada (Llamada/Lead):** Identificación del inmueble/zona.
2.  **Filtro:** Preguntas de cualificación (Dinero, Plazos, Uso).
3.  **Clasificación:**
    * *Cualificado:* Notificación a WhatsApp del comercial (Javier/Jesús) + Registro CRM.
    * *Curioso:* Educación breve + Cierre elegante.
    * *Interesado (No listo):* Nutrición por WhatsApp.