-- 002_sim_relogio_e_falhas.sql
--
-- O relogio virtual e a injecao de falhas.
--
-- Todo o resto do sistema pergunta "que horas sao?" para `sim.now()`, e nunca
-- para `now()`. E isso que permite reproduzir 26 dias de dump em uma sessao de
-- laboratorio, e que faz `available_at` significar alguma coisa.

CREATE TABLE sim.clock (
  id          smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  sim_now     timestamptz NOT NULL,
  speed       numeric     NOT NULL DEFAULT 1.0 CHECK (speed >= 0),
  anchor_wall timestamptz NOT NULL,
  updated_at  timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE sim.clock IS
  'Uma linha so, travada pelo CHECK (id = 1). Duas linhas significariam dois '
  'presentes simultaneos';
COMMENT ON COLUMN sim.clock.speed IS
  '1.0 = tempo real; 60 = um minuto virtual por segundo de parede';
COMMENT ON COLUMN sim.clock.anchor_wall IS
  'relogio de parede no instante do ultimo `set`: e a partir dele que sim.now() '
  'interpola, o que dispensa um tick periodico';

-- Ancora inicial: o primeiro instante do dump. O simulador reposiciona no
-- inicio de cada execucao; este valor existe para que `sim.now()` responda
-- alguma coisa sensata num banco recem-migrado.
INSERT INTO sim.clock (id, sim_now, speed, anchor_wall)
VALUES (1, timestamptz '2026-07-12 00:00:00+00', 1.0, now())
ON CONFLICT (id) DO NOTHING;

-- STABLE, nunca IMMUTABLE. O planner pode avaliar uma vez por statement (que e
-- o que queremos: a view nao pode mudar de resposta no meio da propria
-- varredura), mas nao pode cachear entre statements. IMMUTABLE congelaria o
-- relogio dentro de uma view e o dashboard pararia no tempo sem dar erro.
CREATE FUNCTION sim.now() RETURNS timestamptz
LANGUAGE sql STABLE AS $$
  SELECT sim_now + (now() - anchor_wall) * speed FROM sim.clock WHERE id = 1;
$$;

COMMENT ON FUNCTION sim.now() IS
  'O presente virtual. Todo filtro de available_at passa por aqui';

-- Reposiciona o relogio. Existe como funcao, e nao como UPDATE solto, porque
-- `anchor_wall` PRECISA ser reancorado junto -- esquecer isso faz o tempo
-- virtual dar um salto proporcional a quanto tempo o relogio ficou parado.
CREATE FUNCTION sim.set_clock(p_now timestamptz, p_speed numeric DEFAULT NULL)
RETURNS timestamptz LANGUAGE sql AS $$
  UPDATE sim.clock
     SET sim_now     = p_now,
         speed       = COALESCE(p_speed, speed),
         anchor_wall = now(),
         updated_at  = now()
   WHERE id = 1
  RETURNING sim_now;
$$;

CREATE TABLE sim.run (
  run_id     bigserial PRIMARY KEY,
  seed       bigint      NOT NULL,
  t0         timestamptz NOT NULL,
  t1         timestamptz NOT NULL,
  speed      numeric     NOT NULL,
  status     text        NOT NULL DEFAULT 'pending'
             CHECK (status IN ('pending', 'running', 'paused', 'done')),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (t1 > t0)
);

COMMENT ON COLUMN sim.run.seed IS
  'Duas execucoes com a mesma seed produzem a mesma sequencia de falhas. E o '
  'que permite comparar dois detectores sobre exatamente o mesmo cenario';

CREATE TABLE sim.fault (
  fault_id bigserial PRIMARY KEY,
  run_id   bigint      NOT NULL REFERENCES sim.run ON DELETE CASCADE,
  kind     text        NOT NULL,
  target   jsonb       NOT NULL,
  ts_start timestamptz NOT NULL,
  ts_end   timestamptz NOT NULL,
  params   jsonb       NOT NULL DEFAULT '{}',
  CHECK (ts_end > ts_start)
);

COMMENT ON COLUMN sim.fault.kind IS
  'error_spike | latency | source_outage | ... -- texto livre de proposito: o '
  'catalogo de falhas ainda vai crescer e nao vale uma migration por tipo novo';
COMMENT ON COLUMN sim.fault.target IS
  '{source, entity, metric} para falha de telemetria, {device_model, uf} para '
  'falha de grain de sessao';

CREATE INDEX ON sim.fault (run_id, ts_start);
