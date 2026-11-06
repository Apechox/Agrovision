// Frontend de AgroVision: HTML + JS puro. Habla con web/server.py por fetch (JSON) y MJPEG.
const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// ---------- contenido didáctico ----------
const EXPLICA_VISTA = {
  detecciones: 'Resultado final del cuadro: contorno de cada tomate, su ID de seguimiento y el ancho en mm. ' +
    'Verde = válido y medido dentro de la zona azul; naranja = cortado por el borde o fuera de la zona.',
  mascara: 'Etapa 2a (seg.py): se convierte la imagen a HSV y se deja en blanco lo que cae dentro del rango de color ' +
    'del tomate (cv2.inRange). Es una máscara cruda: puede traer ruido y huecos.',
  limpia: 'Etapa 2b (seg.py): apertura morfológica (borra puntitos blancos) y cierre (rellena huecos, como reflejos). ' +
    'De esta máscara salen los contornos.',
};
const ETAPAS = [
  { n: 1, t: 'Adquisición', a: 'acq.py', ok: true, vista: 'detecciones',
    d: 'Lee la cámara o el archivo cuadro a cuadro, con índice y marca de tiempo. Si el video termina o la señal se pierde, ' +
       'suspende las observaciones en vez de seguir midiendo (RF1, RF11).' },
  { n: 2, t: 'Segmentación', a: 'seg.py', ok: true, vista: 'mascara',
    d: 'Convierte a HSV, umbraliza por color, limpia con morfología y extrae un contorno por tomate. ' +
       'Marca como inválido el que toca el borde de la imagen (RF2).' },
  { n: 3, t: 'Seguimiento', a: 'track.py', ok: true, vista: 'detecciones',
    d: 'Asocia cada tomate con el del cuadro anterior por distancia entre centroides y le mantiene el mismo ID (RF9).' },
  { n: 4, t: 'Calibración', a: 'calib.py', ok: true, vista: 'detecciones',
    d: 'Convierte el ancho en píxeles a mm (ancho_px / px_por_mm), solo dentro de la zona de medición. ' +
       'La escala todavía NO está validada con pie de metro (RF4).' },
  { n: 5, t: 'Madurez', a: 'madurez.py', ok: false, vista: 'detecciones',
    d: 'Pendiente: el módulo A3.1 no está integrado en el repositorio (RF3).' },
  { n: 6, t: 'Manchas', a: 'manchas.py', ok: false, vista: 'detecciones',
    d: 'Pendiente: el módulo A3.2 no está integrado en el repositorio (RF5).' },
  { n: 7, t: 'Registro', a: 'sesion.py', ok: true, vista: 'detecciones',
    d: 'Guarda una sola fila por ID (la observación más cercana al centro de la zona) y exporta CSV. ' +
       'Es provisional hasta integrar el módulo M6 (RF7).' },
];
const ESTADOS = {
  ESPERANDO: ['Esperando fuente', 'pill-espera'], LISTO: ['Lista para iniciar', 'pill-listo'],
  PROCESANDO: ['Procesando', 'pill-proc'], RESULTADO: ['Resultado', 'pill-res'],
};

// ---------- utilidades ----------
let toastTimer;
function aviso(texto, ok = true) {
  const t = $('#toast');
  t.textContent = texto; t.className = 'toast' + (ok ? '' : ' error'); t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.hidden = true), 4000);
}
async function post(url, opciones = {}) {
  try {
    const r = await fetch(url, { method: 'POST', ...opciones });
    const j = await r.json();
    aviso(j.mensaje, j.ok);
    return j;
  } catch (e) {
    aviso('No se pudo contactar al servidor local.', false);
    return { ok: false };
  }
}
const mm = (v) => (v === null || v === undefined || v === '' ? '—' : Number(v).toFixed(1));

// ---------- vista de video ----------
let vista = 'detecciones';
function elegirVista(v) {
  vista = v;
  document.querySelectorAll('[data-vista]').forEach((b) => b.classList.toggle('activa', b.dataset.vista === v));
  $('#video').src = `/video?vista=${v}&t=${Date.now()}`;
  $('#explica').textContent = EXPLICA_VISTA[v];
}
document.querySelectorAll('[data-vista]').forEach((b) => b.addEventListener('click', () => elegirVista(b.dataset.vista)));

// ---------- etapas del pipeline ----------
$('#etapas').innerHTML = ETAPAS.map((e, i) =>
  `<li><button class="etapa" data-i="${i}"><b>${e.n}. ${esc(e.t)}</b><small>${esc(e.a)}</small><br>` +
  `<span class="chip ${e.ok ? 'ok' : 'pend'}">${e.ok ? 'Integrado' : 'Pendiente'}</span></button></li>`).join('');
document.querySelectorAll('.etapa').forEach((b) => {
  const mostrar = () => {
    const e = ETAPAS[b.dataset.i];
    document.querySelectorAll('.etapa').forEach((x) => x.classList.toggle('sel', x === b));
    $('#etapa-detalle').textContent = `${e.n}. ${e.t} (${e.a}): ${e.d}`;
  };
  b.addEventListener('mouseenter', mostrar);
  b.addEventListener('focus', mostrar);
  b.addEventListener('click', () => { mostrar(); if (ETAPAS[b.dataset.i].n === 2) elegirVista('mascara'); });
});

// ---------- esquema del flujo (modo didáctico) ----------
const FLUJO = [
  { t: 'Video', d: 'Cuadro de la cámara o del archivo (BGR).', m: 'M1 · acq.py', vista: 'detecciones' },
  { t: 'Máscara HSV', d: 'Pasa a HSV y deja en blanco el rango de color del tomate (inRange).', m: 'M2 · seg.py', vista: 'mascara' },
  { t: 'Máscara limpia', d: 'Apertura quita el ruido; cierre rellena huecos.', m: 'M2 · seg.py', vista: 'limpia' },
  { t: 'Detecciones', d: 'Contornos sobre la máscara limpia; marca los que tocan el borde.', m: 'M2 · seg.py', vista: 'detecciones' },
  { t: 'Seguimiento', d: 'Mantiene un ID por tomate entre cuadros.', m: 'M3 · track.py' },
  { t: 'Calibración', d: 'ancho en px ÷ px/mm = mm, dentro de la zona de medición.', m: 'M4 · calib.py' },
  { t: 'Madurez y manchas', d: 'Pendiente: módulos A3.1 y A3.2 aún no integrados.', m: 'M5', pend: true },
  { t: 'Registro', d: 'Una fila por ID; exporta CSV.', m: 'M6 · sesion.py' },
];
$('#flujo').innerHTML = FLUJO.map((p, i) => {
  const cuerpo = `<span class="mod">${esc(p.m)}</span><b>${i + 1}. ${esc(p.t)}</b><small>${esc(p.d)}</small>`;
  return `<li>${p.vista && p.t !== 'Video' && p.t !== 'Detecciones'
    ? `<button class="paso" data-vista-flujo="${p.vista}">${cuerpo}</button>`
    : `<div class="paso${p.pend ? ' pend' : ''}">${cuerpo}</div>`}</li>`;
}).join('');
$('#flujo-nota').textContent = 'Ojo: la máscara HSV no se usa para detectar; solo alimenta a la máscara limpia. ' +
  'Los contornos (las detecciones) salen de la máscara limpia.';
document.querySelectorAll('[data-vista-flujo]').forEach((b) =>
  b.addEventListener('click', () => elegirVista(b.dataset.vistaFlujo)));

// ---------- modo didáctico (se recuerda en este navegador) ----------
function aplicarModoDidactico(activo, guardar = true) {
  document.body.classList.toggle('modo-did', activo);
  $('#modo-did').checked = activo;
  if (!activo && vista !== 'detecciones') elegirVista('detecciones');  // la máscara ya no tiene pestaña
  if (guardar) { try { localStorage.setItem('agrovision.didactico', activo ? '1' : '0'); } catch (e) { /* sin almacenamiento */ } }
  pintarRoi();  // el alto del visor puede cambiar al mostrar u ocultar bloques
}
$('#modo-did').addEventListener('change', (e) => aplicarModoDidactico(e.target.checked));

// ---------- paneles de resultados ----------
let panel = 'p-actual';
function elegirPanel(id) {
  panel = id;
  document.querySelectorAll('[data-panel]').forEach((b) => b.classList.toggle('activa', b.dataset.panel === id));
  document.querySelectorAll('.panel').forEach((p) => (p.hidden = p.id !== id));
  if (id === 'p-dash') Dash.pintar();
}
document.querySelectorAll('[data-panel]').forEach((b) => b.addEventListener('click', () => elegirPanel(b.dataset.panel)));

// ---------- render del estado ----------
let ultimo = '';
function render(s) {
  const firma = JSON.stringify(s);
  if (firma === ultimo) return;
  ultimo = firma;
  defectoHsv = { min: s.hsv.defecto_min, max: s.hsv.defecto_max };
  if (!hsvIniciado) {  // solo la primera vez: después mandan los sliders, no el servidor
    hsvIniciado = true; hsv = { min: [...s.hsv.min], max: [...s.hsv.max] }; pintarSliders();
  }

  const [txt, clase] = s.interrumpida ? ['Fuente interrumpida', 'pill-aviso'] : (ESTADOS[s.estado] || ESTADOS.ESPERANDO);
  const pill = $('#pill'); pill.textContent = '● ' + txt; pill.className = 'pill ' + clase;
  $('#meta').textContent = [s.mensaje, s.ocupado && s.fps ? `${s.fps} FPS de proceso` : '', s.cuadros ? `cuadros: ${s.cuadros}` : '']
    .filter(Boolean).join(' · ');
  $('#aviso-interrupcion').hidden = !s.interrumpida;

  recibirRoi(s.roi);

  $('#btn-iniciar').disabled = !s.cola.some((c) => c.estado === 'En espera') || s.ocupado;
  $('#btn-detener').disabled = !s.ocupado;
  $('#btn-guardar').disabled = !s.puede_guardar;
  pintarCola(s);

  $('#titulo-actual').textContent = s.interrumpida
    ? '⚠ Últimos resultados — anteriores a la interrupción de la fuente'
    : (s.observaciones.length ? `Observaciones actuales: ${s.observaciones.length} objeto(s) en el cuadro` : 'Sin observaciones');
  $('#t-actual').innerHTML = s.observaciones.map((o) =>
    `<tr class="${o.valida ? '' : 'aviso'}"><td>${o.id ?? '—'}</td><td>${o.ancho_px}</td><td>${mm(o.ancho_mm)}</td>` +
    `<td>${esc(o.calibre)}</td><td>${esc(o.madurez)}</td><td>${esc(o.manchas)}</td><td>${esc(o.validez)}</td></tr>`).join('');
  const conMedida = s.observaciones.find((o) => o.ancho_mm !== null);
  $('#estado-calibre').textContent = conMedida ? `Calibre: ${conMedida.estado_calibre}` : (s.calibracion ? `Calibración: ${s.calibracion}` : '');

  const prov = s.registro.filter((r) => r.estado_registro === 'Provisional').length;
  $('#titulo-registro').textContent = `${s.registro.length} registro(s) — ${prov} provisional(es). Una fila por tomate (por ID) de cada archivo, no por cuadro.`;
  $('#t-registro').innerHTML = s.registro.map((r) =>
    `<tr><td>${esc(r.fuente)}</td><td>${r.id}</td><td>${r.cuadro}</td><td>${mm(r.ancho_mm)}</td><td>${esc(r.calibre)}</td><td>${esc(r.estado_registro)}</td></tr>`).join('');

  $('#tab-incid').textContent = `Incidencias${s.incidencias.length ? ` (${s.incidencias.length})` : ''}`;
  $('#lista-incid').innerHTML = s.incidencias.length
    ? s.incidencias.map((i) => `<li><b>${esc(i.hora)} · ${esc(i.origen)}</b> — ${esc(i.causa)} <span class="chico">(${esc(i.fuente)})</span></li>`).join('')
    : '<li class="vacio">Sin incidencias.</li>';
  Dash.setSesion(s.registro);  // el dashboard calcula en el navegador con lo que la página acaba de leer
  if (panel === 'p-dash') Dash.pintar();
}
function pintarCola(s) {
  const caja = $('#cola-caja');
  caja.hidden = s.cola.length === 0;
  const pendientes = s.cola.filter((c) => c.estado === 'En espera').length;
  $('#cola-titulo').textContent = `Cola: ${s.cola.length} archivo(s), ${pendientes} en espera`;
  $('#btn-vaciar').disabled = s.ocupado;
  if (arrastreCola !== null) return;  // no reescribir la lista mientras se arrastra una fila
  const html = s.cola.map((c) => {
    const espera = c.estado === 'En espera';
    const clase = espera ? '' : c.estado === 'Procesando' ? 'est-proc' : c.estado === 'Listo' ? 'est-ok' : 'est-aviso';
    return `<li data-i="${c.i}"${espera ? ' draggable="true"' : ''}>` +
      `<span class="cola-asa" title="${espera ? 'Arrastra para cambiar el orden de análisis' : 'Ya no se puede reordenar'}">☰</span>` +
      `<span class="cola-nombre" title="${esc(c.nombre)}">${c.i + 1}. ${esc(c.nombre)}</span>` +
      `<span class="est ${clase}">${esc(c.tipo)} · ${esc(c.estado)}${c.registros ? ` · ${c.registros} reg.` : ''}</span>` +
      `<button class="cola-x" data-quitar="${c.i}" aria-label="Quitar ${esc(c.nombre)}"` +
      `${c.estado === 'Procesando' ? ' disabled' : ''}>✕</button></li>`;
  }).join('');
  if (html !== colaHtml) { colaHtml = html; $('#cola').innerHTML = html; }
}
let colaHtml = '', arrastreCola = null;
{
  const lista = $('#cola'), limpiar = () => lista.querySelectorAll('.destino, .arrastrando')
    .forEach((x) => x.classList.remove('destino', 'arrastrando'));
  lista.addEventListener('dragstart', (e) => {
    const li = e.target.closest('li[draggable="true"]'); if (!li) return;
    arrastreCola = Number(li.dataset.i); li.classList.add('arrastrando');
    e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', String(arrastreCola));
  });
  lista.addEventListener('dragover', (e) => {
    if (arrastreCola === null) return;
    e.preventDefault();
    const li = e.target.closest('li'); lista.querySelectorAll('.destino').forEach((x) => x.classList.remove('destino'));
    if (li) li.classList.add('destino');
  });
  lista.addEventListener('drop', async (e) => {
    if (arrastreCola === null) return;
    e.preventDefault();
    const li = e.target.closest('li'), de = arrastreCola;
    arrastreCola = null; limpiar();
    if (li && Number(li.dataset.i) !== de) { await post(`/api/cola/mover?de=${de}&a=${li.dataset.i}`); refrescar(); }
  });
  lista.addEventListener('dragend', () => { arrastreCola = null; limpiar(); });
}
async function refrescar() {
  try { render(await (await fetch('/api/estado', { cache: 'no-store' })).json()); }
  catch (e) { $('#pill').textContent = '● Sin conexión con el servidor'; $('#pill').className = 'pill pill-aviso'; }
}

// ---------- dashboard ----------
// La lógica vive en dashboard.js (Dash): lee la sesión actual o un CSV cargado.
Dash.iniciar();

// ---------- zona de medición (ROI) arrastrable ----------
const ROI_MIN = 20, roiEl = $('#roi');
let roi = null, cuadro = null, arrastre = null, roiTimer, roiIgnorarHasta = 0;
const acotar = (v, a, b) => Math.max(a, Math.min(b, v));

function recibirRoi(r) {
  cuadro = r.cuadro;
  // el servidor entrega la zona vigente (por defecto, el cuadro completo); no pisar lo que el usuario mueve
  if (!arrastre && Date.now() > roiIgnorarHasta) roi = r.valor ? [...r.valor] : null;
  pintarRoi();
}
function geom() {  // dónde se dibuja el fotograma dentro del visor (el <img> usa object-fit: contain)
  if (!cuadro) return null;
  const img = $('#video'), r = img.getBoundingClientRect(), v = img.parentElement.getBoundingClientRect();
  const k = Math.min(r.width / cuadro[0], r.height / cuadro[1]);
  if (!(k > 0)) return null;
  return { k, nw: cuadro[0], nh: cuadro[1],
    x0: r.left - v.left + (r.width - cuadro[0] * k) / 2, y0: r.top - v.top + (r.height - cuadro[1] * k) / 2 };
}
function roiVisible() {  // la zona original puede salirse de la imagen: se muestra recortada
  const [x, y, w, h] = roi, [W, H] = cuadro;
  const x1 = acotar(x, 0, W - ROI_MIN), y1 = acotar(y, 0, H - ROI_MIN);
  return [x1, y1, acotar(x + w, x1 + ROI_MIN, W) - x1, acotar(y + h, y1 + ROI_MIN, H) - y1];
}
function pintarRoi() {
  const g = geom();
  if (!g || !roi) { roiEl.hidden = true; return; }
  const [x, y, w, h] = roiVisible();
  roiEl.hidden = false;
  Object.assign(roiEl.style, { left: `${g.x0 + x * g.k}px`, top: `${g.y0 + y * g.k}px`, width: `${w * g.k}px`, height: `${h * g.k}px` });
  const completa = x === 0 && y === 0 && w === g.nw && h === g.nh;
  $('#roi-txt').textContent = `Zona de medición: x ${x}, y ${y}, ${w} × ${h} px` + (completa ? ' (cuadro completo)' : '');
}
roiEl.addEventListener('pointerdown', (e) => {
  const g = geom(); if (!g || !roi) return;
  roi = roiVisible();
  arrastre = { h: e.target.dataset.h || 'mover', px: e.clientX, py: e.clientY, r0: [...roi], g };
  roiEl.setPointerCapture(e.pointerId); e.preventDefault();
});
roiEl.addEventListener('pointermove', (e) => {
  if (!arrastre) return;
  const { h, px, py, r0, g } = arrastre;
  const dx = Math.round((e.clientX - px) / g.k), dy = Math.round((e.clientY - py) / g.k);
  const [x, y, w, alto] = r0;
  if (h === 'mover') {
    roi = [acotar(x + dx, 0, g.nw - w), acotar(y + dy, 0, g.nh - alto), w, alto];
  } else {
    let x1 = x, y1 = y, x2 = x + w, y2 = y + alto;
    if (h.includes('w')) x1 = acotar(x1 + dx, 0, x2 - ROI_MIN);
    if (h.includes('e')) x2 = acotar(x2 + dx, x1 + ROI_MIN, g.nw);
    if (h.includes('n')) y1 = acotar(y1 + dy, 0, y2 - ROI_MIN);
    if (h.includes('s')) y2 = acotar(y2 + dy, y1 + ROI_MIN, g.nh);
    roi = [x1, y1, x2 - x1, y2 - y1];
  }
  pintarRoi();
  clearTimeout(roiTimer); roiTimer = setTimeout(enviarRoi, 120);
});
const soltarRoi = () => { if (!arrastre) return; arrastre = null; clearTimeout(roiTimer); enviarRoi(); };
roiEl.addEventListener('pointerup', soltarRoi);
roiEl.addEventListener('pointercancel', soltarRoi);
async function enviarRoi() {
  roiIgnorarHasta = Date.now() + 700;  // la respuesta de /api/estado en vuelo podría traer la zona anterior
  try {
    const r = await fetch('/api/roi', { method: 'POST', body: JSON.stringify({ x: roi[0], y: roi[1], w: roi[2], h: roi[3] }) });
    const j = await r.json();
    if (!j.ok) aviso(j.mensaje, false);
  } catch (e) { aviso('No se pudo enviar la zona de medición', false); }
}
$('#btn-roi-reset').addEventListener('click', async () => {
  roiIgnorarHasta = 0;
  await post('/api/roi', { body: JSON.stringify({ completa: true }) });
  refrescar();
});
new ResizeObserver(pintarRoi).observe($('.visor'));
$('#video').addEventListener('load', pintarRoi);

// ---------- sliders HSV ----------
const CANALES = [['H', 179], ['S', 255], ['V', 255]];
let hsv = { min: [0, 70, 50], max: [179, 255, 255] }, hsvIniciado = false, hsvTimer;
const sliders = [];  // {lado, i, input, salida}
CANALES.forEach(([nombre, tope], i) => ['min', 'max'].forEach((lado) => {
  const fila = document.createElement('label'); fila.className = 'slider';
  const etiqueta = document.createElement('span'); etiqueta.textContent = `${nombre} ${lado === 'min' ? 'mín' : 'máx'}`;
  const input = document.createElement('input'); Object.assign(input, { type: 'range', min: 0, max: tope, step: 1 });
  const salida = document.createElement('output');
  input.setAttribute('aria-label', etiqueta.textContent);
  input.addEventListener('input', () => {
    hsv[lado][i] = Number(input.value);
    if (hsv.min[i] > hsv.max[i]) { hsv[lado === 'min' ? 'max' : 'min'][i] = hsv[lado][i]; }  // mantiene mín ≤ máx
    pintarSliders();
    clearTimeout(hsvTimer); hsvTimer = setTimeout(enviarHsv, 120);
  });
  fila.append(etiqueta, input, salida); $('#sliders').append(fila);
  sliders.push({ lado, i, input, salida });
}));
function pintarSliders() {
  sliders.forEach((s) => { s.input.value = hsv[s.lado][s.i]; s.salida.textContent = hsv[s.lado][s.i]; });
}
async function enviarHsv() {
  try {
    const r = await fetch('/api/hsv', { method: 'POST', body: JSON.stringify(hsv) });
    const j = await r.json();
    $('#hsv-nota').textContent = j.mensaje;
    if (!j.ok) aviso(j.mensaje, false);
  } catch (e) { aviso('No se pudo contactar al servidor local.', false); }
}
$('#btn-hsv-reset').addEventListener('click', () => {
  hsv = { min: [...defectoHsv.min], max: [...defectoHsv.max] }; pintarSliders(); enviarHsv();
});
let defectoHsv = { min: [0, 70, 50], max: [179, 255, 255] };
pintarSliders();

// ---------- acciones ----------
async function subir(archivos) {
  for (const archivo of archivos) {  // de a uno: cada archivo entra a la cola en el orden elegido
    aviso(`Subiendo ${archivo.name}…`);
    await post(`/api/fuente/archivo?nombre=${encodeURIComponent(archivo.name)}`,
      { body: archivo, headers: { 'Content-Type': 'application/octet-stream' } });
    await refrescar();
  }
}
const accion = (url) => async () => { await post(url); refrescar(); };
const iniciar = accion('/api/iniciar'), detener = accion('/api/detener'), repetir = async () => {
  if (ultimo && JSON.parse(ultimo).puede_guardar && !confirm('Hay registros que se perderán. ¿Continuar?')) return;
  await post('/api/repetir'); refrescar();
};
async function guardar() {
  if ($('#btn-guardar').disabled) return;
  if (!confirm('¿Guardar los dos CSV (Excel y para programas) y la vista anotada?')) return;
  const descargas = [['/api/registro.csv?formato=excel', 'registro.csv'], ['/api/registro.csv?formato=datos', 'registro_datos.csv'],
    ['/api/vista.png', 'vista_anotada.png']];
  for (const [url, nombre] of descargas) {
    const a = document.createElement('a'); a.href = url; a.download = nombre; document.body.append(a); a.click(); a.remove();
    await new Promise((r) => setTimeout(r, 300));  // espacio entre descargas para que el navegador no las agrupe
  }
}
$('#btn-iniciar').addEventListener('click', iniciar);
$('#btn-detener').addEventListener('click', detener);
$('#btn-guardar').addEventListener('click', guardar);
$('#btn-vaciar').addEventListener('click', async () => {
  if (ultimo && JSON.parse(ultimo).puede_guardar && !confirm('Hay registros que se perderán. ¿Vaciar la cola?')) return;
  await post('/api/cola/vaciar'); refrescar();
});
$('#cola').addEventListener('click', async (e) => {
  const b = e.target.closest('[data-quitar]'); if (!b || b.disabled) return;
  await post(`/api/cola/quitar?i=${b.dataset.quitar}`); refrescar();
});
$('#btn-repetir').addEventListener('click', repetir);
$('#btn-muestra').addEventListener('click', accion('/api/fuente/muestra'));
$('#btn-camara').addEventListener('click', async () => {
  await post(`/api/fuente/camara?n=${encodeURIComponent($('#camara-n').value || 0)}`); refrescar();
});

const zona = $('#zona'), input = $('#archivo');
zona.addEventListener('click', () => input.click());
zona.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') input.click(); });
input.addEventListener('change', () => { const f = [...input.files]; input.value = ''; if (f.length) subir(f); });
['dragenter', 'dragover'].forEach((ev) => zona.addEventListener(ev, (e) => { e.preventDefault(); zona.classList.add('sobre'); }));
['dragleave', 'drop'].forEach((ev) => zona.addEventListener(ev, (e) => { e.preventDefault(); zona.classList.remove('sobre'); }));
zona.addEventListener('drop', (e) => { const f = [...e.dataTransfer.files]; if (f.length) subir(f); });

document.addEventListener('keydown', (e) => {
  if (e.ctrlKey || e.metaKey || e.altKey || ['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;
  const k = e.key.toLowerCase();
  if (k === 'q') input.click(); else if (k === 'w') iniciar(); else if (k === 's' || k === 'escape') detener();
  else if (k === 'e') guardar(); else if (k === 'r') repetir(); else if (k === 'd') elegirPanel('p-dash');
});

let didInicial = false;
try { didInicial = localStorage.getItem('agrovision.didactico') === '1'; } catch (e) { /* sin almacenamiento */ }
elegirVista('detecciones');
aplicarModoDidactico(didInicial, false);
refrescar();
setInterval(refrescar, 300);
