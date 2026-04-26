import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const PIPELINE_STEPS = [
  { title: 'Classify', text: 'Определяем лекарственную форму' },
  { title: 'Extract', text: 'Достаём визуальные признаки' },
  { title: 'Normalize', text: 'Проверяем JSON и ищем top-5' },
];

const FORM_OPTIONS = [
  { value: '', label: 'Все формы' },
  { value: 'soft_capsule', label: 'soft capsule' },
  { value: 'capsule', label: 'capsule' },
  { value: 'tablet', label: 'tablet' },
  { value: 'film_tablet', label: 'film tablet' },
  { value: 'caplet', label: 'caplet' },
];

function JsonBlock({ title, value, initiallyOpen = false }) {
  return (
    <details className="jsonBox" open={initiallyOpen}>
      <summary>{title}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

function UploadIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="uploadIcon">
      <path d="M12 16V4m0 0 4.5 4.5M12 4 7.5 8.5" />
      <path d="M20 16.5v1.25A2.25 2.25 0 0 1 17.75 20H6.25A2.25 2.25 0 0 1 4 17.75V16.5" />
    </svg>
  );
}

function LoadingPanel() {
  return (
    <div className="loadingPanel" role="status" aria-live="polite">
      <div className="orbWrap">
        <div className="orb" />
        <div className="pill pillOne" />
        <div className="pill pillTwo" />
      </div>
      <div>
        <h3>Модель анализирует изображение</h3>
        <p>Qwen проходит 3 этапа: форма → признаки → нормализация. Это может занять немного времени, особенно на CPU.</p>
        <div className="pipelineMini">
          {PIPELINE_STEPS.map((step, index) => (
            <div className="pipelineStep active" key={step.title} style={{ animationDelay: `${index * 0.18}s` }}>
              <span>{index + 1}</span>
              <div>
                <strong>{step.title}</strong>
                <small>{step.text}</small>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function DrugCard({ drug }) {
  const chips = [
    drug.dosage_form,
    drug.shape,
    drug.profile,
    drug.color_primary,
    drug.translucency,
    drug.surface,
  ].filter(Boolean);

  return (
    <article className="drugCard">
      <div className="drugTop">
        <div>
          <h3>{drug.trade_name || 'Без названия'}</h3>
          <p>{drug.inn || 'МНН не указан'}{drug.dosage ? ` · ${drug.dosage}` : ''}</p>
        </div>
        <span className="drugForm">{drug.dosage_form || 'unknown'}</span>
      </div>

      <p className="drugDescription">{drug.free_description || drug.original_text || 'Описание отсутствует.'}</p>

      <div className="drugMeta">
        <span><b>Производитель:</b> {drug.manufacturer || 'не указан'}</span>
        <span><b>Маркировка:</b> {drug.imprint_text || 'нет'}</span>
        <span><b>Логотип:</b> {drug.logo_or_symbol || 'нет'}</span>
      </div>

      <div className="chips catalogChips">
        {chips.length ? chips.map((chip) => <span key={`${drug.id}-${chip}`}>{chip}</span>) : <span>визуальные признаки не указаны</span>}
      </div>
    </article>
  );
}

function CatalogTab() {
  const [query, setQuery] = useState('');
  const [form, setForm] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [catalog, setCatalog] = useState({ total: 0, items: [] });

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setLoading(true);
      setError('');
      try {
        const params = new URLSearchParams({ limit: '300' });
        if (query.trim()) params.set('q', query.trim());
        if (form) params.set('dosage_form', form);

        const response = await fetch(`/api/drugs?${params.toString()}`, { signal: controller.signal });
        const json = await response.json();
        if (!response.ok) throw new Error(json.error || 'Не удалось загрузить список препаратов');
        setCatalog(json);
      } catch (err) {
        if (err.name !== 'AbortError') setError(err.message);
      } finally {
        setLoading(false);
      }
    }, 220);

    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [query, form]);

  return (
    <section className="catalogArea">
      <div className="catalogHeader card">
        <div>
          <p className="eyebrow">База данных</p>
          <h2>Лекарственные средства</h2>
          <p>Здесь показаны все записи из таблицы <code>drug_profiles</code>. Этот список помогает быстро понять, с какими препаратами сейчас сравнивается фото.</p>
        </div>
        <div className="catalogCounter">
          <strong>{catalog.total}</strong>
          <span>записей найдено</span>
        </div>
      </div>

      <div className="catalogControls card">
        <label>
          <span>Поиск</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Название, цвет, форма, маркировка..."
          />
        </label>
        <label>
          <span>Форма</span>
          <select value={form} onChange={(event) => setForm(event.target.value)}>
            {FORM_OPTIONS.map((option) => (
              <option value={option.value} key={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
      </div>

      {loading && (
        <div className="catalogLoading card">
          <span className="spinner dark" />
          <strong>Загружаем препараты из PostgreSQL...</strong>
        </div>
      )}

      {error && <p className="error">{error}</p>}

      {!loading && !error && !catalog.items.length && (
        <div className="emptyState card">
          <div className="emptyIcon">⌕</div>
          <strong>Ничего не найдено</strong>
          <p>Попробуй изменить строку поиска или сбросить фильтр формы.</p>
        </div>
      )}

      <div className="drugGrid">
        {catalog.items.map((drug) => <DrugCard drug={drug} key={drug.id} />)}
      </div>
    </section>
  );
}

function AnalyzeTab() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState('');
  const [loading, setLoading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  const top = useMemo(() => data?.results ?? [], [data]);
  const best = top[0];
  const modelMode = data?.model_mode || 'waiting';

  function setSelectedFile(selected) {
    setFile(selected || null);
    setData(null);
    setError('');

    if (preview) URL.revokeObjectURL(preview);
    setPreview(selected ? URL.createObjectURL(selected) : '');
  }

  function onFileChange(event) {
    setSelectedFile(event.target.files?.[0]);
  }

  function onDrop(event) {
    event.preventDefault();
    setDragging(false);
    const selected = event.dataTransfer.files?.[0];
    if (selected) setSelectedFile(selected);
  }

  async function analyze() {
    if (!file) {
      setError('Выбери фото таблетки или капсулы.');
      return;
    }

    setLoading(true);
    setError('');
    setData(null);

    const formData = new FormData();
    formData.append('image', file);

    try {
      const response = await fetch('/api/analyze', {
        method: 'POST',
        body: formData,
      });
      const json = await response.json();
      if (!response.ok) throw new Error(json.error || 'Ошибка анализа');
      setData(json);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <section className="layout">
        <aside className="card uploadCard">
          <div className="cardHead">
            <div>
              <p className="eyebrow">Шаг 1</p>
              <h2>Фото</h2>
            </div>
            <span className={`mode ${modelMode}`}>{modelMode}</span>
          </div>

          <label
            className={`dropzone ${dragging ? 'dragging' : ''} ${preview ? 'hasPreview' : ''}`}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            <input type="file" accept="image/*" onChange={onFileChange} />
            {preview ? (
              <img className="preview" src={preview} alt="preview" />
            ) : (
              <div className="dropPlaceholder">
                <UploadIcon />
                <strong>Перетащи фото сюда</strong>
                <span>или нажми, чтобы выбрать файл</span>
              </div>
            )}
          </label>

          {file && (
            <div className="fileInfo">
              <span>{file.name}</span>
              <small>{Math.max(1, Math.round(file.size / 1024))} KB</small>
            </div>
          )}

          <button className="primaryButton" onClick={analyze} disabled={loading}>
            {loading ? <span className="spinner" /> : <span className="buttonIcon">↗</span>}
            {loading ? 'Анализируем...' : 'Найти похожие'}
          </button>

          {error && <p className="error">{error}</p>}

          {data?.model_mode === 'mock' && (
            <p className="hint">Включён mock-режим. Для реальной модели поставь <code>MODEL_MODE=lmstudio</code> в <code>.env</code>.</p>
          )}
          {data?.model_mode === 'lmstudio' && (
            <p className="hint success">Используется LM Studio / OpenAI-compatible endpoint.</p>
          )}
        </aside>

        <section className="mainColumn">
          {loading && <LoadingPanel />}

          <div className="card resultsCard">
            <div className="cardHead">
              <div>
                <p className="eyebrow">Шаг 2</p>
                <h2>Top-5 похожих</h2>
              </div>
              {best && <span className="bestBadge">Лучшее совпадение: {best.score_percent}%</span>}
            </div>

            {!top.length && !loading && (
              <div className="emptyState">
                <div className="emptyIcon">◎</div>
                <strong>Пока нет результатов</strong>
                <p>Загрузи изображение и запусти анализ. Здесь появятся ближайшие препараты из БД.</p>
              </div>
            )}

            <div className="results">
              {top.map((item, index) => (
                <article className="result" key={item.drug.id} style={{ '--score': `${item.score_percent}%` }}>
                  <div className="rank">#{index + 1}</div>
                  <div className="resultBody">
                    <div className="resultHeader">
                      <div>
                        <strong>{item.drug.trade_name}</strong>
                        <small>{item.drug.inn || 'INN не указан'} · {item.drug.dosage || 'дозировка не указана'}</small>
                      </div>
                      <span>{item.score_percent}%</span>
                    </div>
                    <div className="scoreBar"><i /></div>
                    <p>{item.drug.free_description || 'Описание отсутствует'}</p>
                    <div className="chips">
                      <span>{item.drug.dosage_form || 'form ?'}</span>
                      <span>{item.drug.shape || 'shape ?'}</span>
                      <span>{item.drug.color_primary || 'color ?'}</span>
                      <span>imprint: {item.drug.imprint_text || 'none'}</span>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>
      </section>

      {data && (
        <section className="debugArea">
          <div className="debugHeader">
            <div>
              <p className="eyebrow">Шаг 3</p>
              <h2>Технический вывод</h2>
            </div>
            <p>Можно быстро проверить, что именно вернула модель и как backend нормализовал признаки перед поиском.</p>
          </div>

          <div className="debugGrid">
            <JsonBlock title="Итоговый JSON модели" value={data.extracted_json} initiallyOpen />
            <JsonBlock title="Нормализованный запрос" value={data.normalized_query} initiallyOpen />
            <JsonBlock title="3-stage pipeline" value={data.model_steps} />
          </div>
        </section>
      )}
    </>
  );
}

function App() {
  const [activeTab, setActiveTab] = useState('analyze');

  return (
    <main className="page">
      <section className="hero">
        <div className="heroGlow" />
        <div className="heroContent">
          <p className="badge">baseline demo · LM Studio · Qwen</p>
          <h1>Pill Vision</h1>
          <p className="subtitle">Загрузи фото таблетки или капсулы — система извлечёт JSON-признаки через visual model и покажет top-5 похожих лекарств из PostgreSQL.</p>
          <div className="heroStats">
            <span>3-stage pipeline</span>
            <span>JSON features</span>
            <span>Top-5 search</span>
            <span>Drug catalog</span>
          </div>
        </div>
      </section>

      <nav className="tabs" aria-label="Основные разделы">
        <button className={activeTab === 'analyze' ? 'active' : ''} onClick={() => setActiveTab('analyze')}>
          Анализ фото
        </button>
        <button className={activeTab === 'catalog' ? 'active' : ''} onClick={() => setActiveTab('catalog')}>
          База лекарств
        </button>
      </nav>

      {activeTab === 'analyze' ? <AnalyzeTab /> : <CatalogTab />}
    </main>
  );
}

createRoot(document.getElementById('root')).render(<App />);
