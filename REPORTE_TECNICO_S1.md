\# Reporte Técnico S1 — NEXA Agent



\## Agent Challenge 2026



\*\*Proyecto:\*\* NEXA Agent  

\*\*Hito:\*\* S1 — Agente corriendo end-to-end  

\*\*Fecha:\*\* 17 de octubre de 2026  

\*\*Repositorio:\*\* https://github.com/vaguzmang/nexa-agent



\---



\## 1. Resumen del proyecto



NEXA es un agente educativo basado en inteligencia artificial cuyo propósito es detectar dificultades de aprendizaje a partir de las respuestas de los estudiantes y proponer intervenciones pedagógicas orientadas a corregir esas dificultades.



El objetivo a largo plazo es que NEXA pueda identificar brechas de aprendizaje, seleccionar acciones educativas, verificar posteriormente si la dificultad fue superada y realizar seguimiento del proceso del estudiante.



Para el hito S1 se implementó únicamente el flujo mínimo end-to-end requerido por el Agent Challenge.



\---



\## 2. Objetivo de S1



El objetivo de esta primera entrega fue demostrar que NEXA puede ejecutar correctamente el siguiente flujo:



1\. Recibir una entrada.

2\. Procesarla mediante el agente.

3\. Realizar una llamada real a Grok utilizando la API proporcionada por el Agent Challenge.

4\. Interpretar la situación educativa.

5\. Entregar una salida útil y estructurada.



No se busca todavía implementar el producto completo.



\---



\## 3. Problema que aborda NEXA



En los procesos educativos, una respuesta incorrecta permite saber que existe un error, pero no necesariamente permite comprender por qué ocurrió.



Dos estudiantes pueden entregar la misma respuesta incorrecta por razones completamente diferentes:



\- error de cálculo;

\- confusión conceptual;

\- interpretación incorrecta;

\- omisión;

\- aplicación incorrecta de un procedimiento;

\- desconocimiento del tema.



NEXA busca ir más allá de identificar si una respuesta es correcta o incorrecta.



Su propósito es analizar la respuesta y generar una hipótesis inicial sobre la dificultad que presenta el estudiante para posteriormente proponer una intervención educativa.



\---



\## 4. Flujo implementado



La versión S1 recibe tres datos:



\- pregunta;

\- respuesta correcta;

\- respuesta entregada por el estudiante.



El flujo actual es:



```text

Usuario

&#x20;  ↓

main.py

&#x20;  ↓

NEXA

&#x20;  ↓

prompt.py

&#x20;  ↓

grok\_client.py

&#x20;  ↓

API del Agent Challenge

&#x20;  ↓

Grok

&#x20;  ↓

Análisis educativo

&#x20;  ↓

Resultado estructurado

