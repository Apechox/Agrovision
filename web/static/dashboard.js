// Dashboard de AgroVision. Calcula y dibuja los indicadores a partir de filas normalizadas.
// Los datos pueden venir de la sesión actual (lo que la página acaba de leer) o de un CSV
// exportado antes (formato Excel con ";" o formato de datos con ","). Todo se calcula en el
// navegador: el CSV cargado no se sube a ningún lado.
(function (global) {
  'use strict';

  // ---------- lectura y normalización ----------
  const quitarAcentos = (s) => String(s).normalize('NFD').replace(/[̀-ͯ]/g, '');
  const clave = (s) => quitarAcentos(s).toLowerCase().replace(/[^a-z0-9]/g, '');
  // encabezado (en cualquiera de los dos formatos de CSV) -> campo interno
  const ALIAS = {
    fuente: 'fuente', id: 'id', tipo: 'tipo', anchomm: 'ancho_mm', calibre: 'calibre', madurez: 'madurez',
    manchas: 'manchas', estadodelregistro: 'estado', estadoregistro: 'estado',
    estadodelcalibre: 'estado_calibre', estadocalibre: 'estado_calibre', sesion: 'sesion',
  };
  const REQUERIDAS = ['ancho_mm', 'calibre', 'estado'];
  const PROVISIONAL = 'Provisional';

  function separador(texto) {
    const fin = texto.search(/\r?\n/);
    const cabecera = fin >= 0 ? texto.slice(0, fin) : texto;
    return cabecera.split(';').length > cabecera.split(',').length ? ';' : ',';
  }

  function tablaCSV(texto, sep) {  // lector con comillas; no depende de librerías
    const filas = []; let fila = [], celda = '', enComillas = false;
    for (let i = 0; i < texto.length; i++) {
      const c = texto[i];
      if (enComillas) {
        if (c === '"') { if (texto[i + 1] === '"') { celda += '"'; i++; } else enComillas = false; } else celda += c;
      } else if (c === '"') enComillas = true;
      else if (c === sep) { fila.push(celda); celda = ''; }
      else if (c === '\n') { fila.push(celda); filas.push(fila); fila = []; celda = ''; }
      else if (c !== '\r') celda += c;
    }
    if (celda !== '' || fila.length) { fila.push(celda); filas.push(fila); }
    return filas.filter((f) => f.some((c) => c.trim() !== ''));
  }

  const numero = (v) => {
    if (v === null || v === undefined || String(v).trim() === '') return null;
    const n = Number(String(v).trim().replace(',', '.'));
    return Number.isFinite(n) ? n : null;
  };

  function normalizar(o) {
    return {
      fuente: String(o.fuente || '').trim() || '(sin nombre)', id: o.id ?? '', tipo: String(o.tipo || '').trim(),
      ancho_mm: numero(o.ancho_mm), calibre: String(o.calibre || '').trim(), madurez: String(o.madurez || '').trim(),
      manchas: String(o.manchas || '').trim(), estado: String(o.estado || '').trim(),
      estado_calibre: String(o.estado_calibre || '').trim(),
    };
  }

  function leerCSV(texto) {
    texto = String(texto).replace(/^﻿/, '');
    const tabla = tablaCSV(texto, separador(texto));
    if (tabla.length < 2) return { error: 'El archivo no tiene filas de datos.' };
    const campos = tabla[0].map((c) => ALIAS[clave(c)] || null);
    const faltan = REQUERIDAS.filter((k) => !campos.includes(k));
    if (faltan.length) return { error: `No parece un CSV de AgroVision: faltan las columnas ${faltan.join(', ')}.` };
    const filas = tabla.slice(1).map((f) => {
      const o = {}; campos.forEach((k, i) => { if (k) o[k] = (f[i] ?? '').trim(); });
      return normalizar(o);
    });
    return { filas };
  }

  const desdeSesion = (registro) => registro.map((r) => normalizar({ ...r, estado: r.estado_registro }));

  // ---------- cálculo ----------
  const base = (tipo) => String(tipo).split(' (')[0].trim();  // "Tomate (asumido, ...)" -> "Tomate"

  function estadistica(valores) {
    const n = valores.length;
    if (!n) return { n: 0 };
    const media = valores.reduce((a, b) => a + b, 0) / n;
    const desv = n > 1 ? Math.sqrt(valores.reduce((a, b) => a + (b - media) ** 2, 0) / (n - 1)) : 0;
    return { n, media, min: Math.min(...valores), max: Math.max(...valores), desv };
  }

  function contar(filas, campo) {
    const m = {};
    filas.forEach((f) => { if (f[campo]) m[f[campo]] = (m[f[campo]] || 0) + 1; });
    return m;
  }

  function histograma(valores, tramos = 8) {
    if (!valores.length) return [];
    const min = Math.min(...valores), max = Math.max(...valores);
    const ancho = Math.max(1, Math.ceil((max - min) / tramos));
    const desde = Math.floor(min / ancho) * ancho;
    const cajas = Math.floor((max - desde) / ancho) + 1;
    const res = Array.from({ length: cajas }, (_, i) => ({ desde: desde + i * ancho, hasta: desde + (i + 1) * ancho, n: 0 }));
    valores.forEach((v) => { res[Math.min(Math.floor((v - desde) / ancho), cajas - 1)].n++; });
    return res;
  }

  function resumenPorArchivo(filas) {
    const grupos = {};
    filas.forEach((f) => { (grupos[f.fuente] = grupos[f.fuente] || []).push(f); });
    return Object.entries(grupos).map(([fuente, fs]) => {
      const c = contar(fs, 'calibre'), pred = Object.entries(c).sort((a, b) => b[1] - a[1])[0];
      return { fuente, n: fs.length, ancho: estadistica(fs.map((f) => f.ancho_mm).filter((v) => v !== null)),
        calibre: pred ? pred[0] : '—' };
    });
  }

  function calcular(filas, filtros) {
    const visibles = filas.filter((f) => (!filtros.archivo || f.fuente === filtros.archivo) &&
      (!filtros.fruto || base(f.tipo) === filtros.fruto));
    const definitivas = visibles.filter((f) => f.estado !== PROVISIONAL);  // M6: los provisionales no entran
    const anchos = definitivas.map((f) => f.ancho_mm).filter((v) => v !== null);
    return {
      visibles, definitivas, provisionales: visibles.length - definitivas.length,
      ancho: estadistica(anchos), histograma: histograma(anchos),
      calibre: contar(definitivas, 'calibre'), madurez: contar(definitivas, 'madurez'),
      manchas: contar(definitivas, 'manchas'), estados: contar(visibles, 'estado'),
      porArchivo: resumenPorArchivo(definitivas),
      estimadas: definitivas.some((f) => /estimad/i.test(f.estado_calibre)),
    };
  }

  // ---------- dibujo ----------
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const f1 = (v) => (v === null || v === undefined ? '—' : Number(v).toFixed(1).replace('.', ','));
  const ORDEN_CALIBRE = ['Pequeño', 'Mediano', 'Grande'];

  function barras(titulo, datos, vacio, orden) {
    const total = Object.values(datos).reduce((a, b) => a + b, 0);
    const claves = Object.keys(datos).sort((a, b) => {
      const ia = orden ? orden.indexOf(a) : -1, ib = orden ? orden.indexOf(b) : -1;
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || datos[b] - datos[a];
    });
    const filas = total ? claves.map((k) =>
      `<div class="barra-fila"><span>${esc(k)}</span><div class="barra-pista"><div class="barra-valor" style="width:${(datos[k] / total) * 100}%"></div></div>` +
      `<span>${datos[k]} (${Math.round((datos[k] / total) * 100)}%)</span></div>`).join('') : `<p class="chico">${esc(vacio)}</p>`;
    return `<div class="grafica"><h3>${esc(titulo)}</h3>${filas}</div>`;
  }

  function dibujarHistograma(h) {
    if (!h.length) return '<div class="grafica"><h3>Distribución del ancho (mm)</h3><p class="chico">Sin datos</p></div>';
    const tope = Math.max(...h.map((c) => c.n));
    const cols = h.map((c) => `<div class="hist-col" title="${c.desde}–${c.hasta} mm: ${c.n}">` +
      `<span class="hist-n">${c.n || ''}</span><div class="hist-barra" style="height:${(c.n / tope) * 100}%"></div>` +
      `<span class="hist-x">${c.desde}</span></div>`).join('');
    return `<div class="grafica"><h3>Distribución del ancho (mm)</h3><div class="hist">${cols}</div>` +
      `<p class="chico">Cada barra agrupa ${h[0].hasta - h[0].desde} mm; el número bajo la barra es su inicio.</p></div>`;
  }

  function dibujarKpis(r, filas) {
    const a = r.ancho, archivos = new Set(r.definitivas.map((f) => f.fuente)).size;
    const k = (t, v) => `<div class="kpi"><b>${v}</b><span>${esc(t)}</span></div>`;
    return k('Tomates definitivos', r.definitivas.length) + k('Ancho medio (mm)', a.n ? f1(a.media) : '—') +
      k('Mínimo (mm)', a.n ? f1(a.min) : '—') + k('Máximo (mm)', a.n ? f1(a.max) : '—') +
      k('Desv. estándar (mm)', a.n ? f1(a.desv) : '—') + k('Archivos', archivos);
  }

  function dibujarTabla(filas) {
    if (!filas.length) return '';
    return '<div class="grafica"><h3>Resumen por archivo</h3><div class="tabla-caja"><table><thead><tr>' +
      '<th>Archivo</th><th>Tomates</th><th>Ancho medio (mm)</th><th>Calibre predominante</th></tr></thead><tbody>' +
      filas.map((f) => `<tr><td>${esc(f.fuente)}</td><td>${f.n}</td><td>${f.ancho.n ? f1(f.ancho.media) : '—'}</td>` +
        `<td>${esc(f.calibre)}</td></tr>`).join('') + '</tbody></table></div></div>';
  }

  // ---------- estado y eventos ----------
  const est = { origen: 'sesion', actual: [], csv: null, archivo: '', fruto: '' };
  const $ = (s) => document.querySelector(s);

  function llenar(select, opciones, valor, todos) {
    const html = `<option value="">${todos}</option>` + opciones.map((o) => `<option value="${esc(o)}">${esc(o)}</option>`).join('');
    if (select.dataset.firma !== html) { select.innerHTML = html; select.dataset.firma = html; }
    select.value = opciones.includes(valor) ? valor : '';
  }

  function pintar() {
    if (!$('#p-dash') || $('#p-dash').hidden) return;
    const filas = est.origen === 'csv' ? (est.csv ? est.csv.filas : []) : est.actual;
    llenar($('#dash-f-archivo'), [...new Set(filas.map((f) => f.fuente))], est.archivo, 'Todos');
    llenar($('#dash-f-fruto'), [...new Set(filas.map((f) => base(f.tipo)).filter(Boolean))], est.fruto, 'Todos');
    est.archivo = $('#dash-f-archivo').value; est.fruto = $('#dash-f-fruto').value;
    $('#dash-nombre').textContent = est.csv ? `CSV cargado: ${est.csv.nombre} (${est.csv.filas.length} filas)` : 'Ningún CSV cargado';

    if (!filas.length) {
      $('#titulo-dash').textContent = est.origen === 'csv'
        ? 'Carga un CSV exportado desde AgroVision para ver sus gráficas.'
        : 'Todavía no hay registros: procesa archivos o carga un CSV.';
      $('#dash-kpi').innerHTML = ''; $('#graficas').innerHTML = '';
      return;
    }
    const r = calcular(filas, { archivo: est.archivo, fruto: est.fruto });
    const origen = est.origen === 'csv' ? `CSV «${est.csv.nombre}»` : 'sesión actual';
    $('#titulo-dash').textContent = `Origen: ${origen} · Registros definitivos: ${r.definitivas.length} ` +
      `(provisionales excluidos: ${r.provisionales})` + (r.estimadas ? ' · Medidas estimadas: calibración pendiente de validar' : '');
    $('#dash-kpi').innerHTML = dibujarKpis(r, filas);
    $('#graficas').innerHTML =
      barras('Calibre aparente', r.calibre, 'Sin datos', ORDEN_CALIBRE) +
      dibujarHistograma(r.histograma) +
      barras('Madurez visual', r.madurez, 'Sin datos: módulo A3.1 pendiente') +
      barras('Calidad visual (manchas)', r.manchas, 'Sin datos: módulo A3.2 pendiente') +
      barras('Estado del registro', r.estados, 'Sin datos') +
      dibujarTabla(r.porArchivo) +
      '<p class="chico">Los cortes de calibre (55 y 70 mm) son provisionales hasta que el equipo defina los oficiales.</p>';
  }

  async function cargar(archivo) {
    try {
      const r = leerCSV(await archivo.text());
      if (r.error) { if (global.aviso) global.aviso(r.error, false); return; }
      est.csv = { nombre: archivo.name, filas: r.filas }; est.origen = 'csv'; est.archivo = est.fruto = '';
      document.querySelector('input[name="dash-origen"][value="csv"]').checked = true;
      if (global.aviso) global.aviso(`CSV cargado: ${r.filas.length} filas`);
      pintar();
    } catch (e) { if (global.aviso) global.aviso('No se pudo leer el archivo.', false); }
  }

  function iniciar() {
    document.querySelectorAll('input[name="dash-origen"]').forEach((r) =>
      r.addEventListener('change', () => { est.origen = r.value; est.archivo = est.fruto = ''; pintar(); }));
    $('#dash-cargar').addEventListener('click', () => $('#dash-archivo').click());
    $('#dash-archivo').addEventListener('change', (e) => { const f = e.target.files[0]; e.target.value = ''; if (f) cargar(f); });
    $('#dash-f-archivo').addEventListener('change', (e) => { est.archivo = e.target.value; pintar(); });
    $('#dash-f-fruto').addEventListener('change', (e) => { est.fruto = e.target.value; pintar(); });
  }

  global.Dash = { iniciar, pintar, setSesion: (registro) => { est.actual = desdeSesion(registro); }, leerCSV, calcular, histograma };
  if (typeof module !== 'undefined') module.exports = global.Dash;
})(typeof window !== 'undefined' ? window : globalThis);
