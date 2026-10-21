/**
 * Builds form sections from the backend's live JSON Schema (GET /schema),
 * so the form can never drift from the Pydantic models. The old hand-written
 * configSchema.ts was deleted in favour of this generator.
 */

export type FieldType =
  | 'number'
  | 'text'
  | 'boolean'
  | 'select'
  | 'multiselect';

export interface FieldDef {
  key: string;
  label: string;
  type: FieldType;
  options?: string[];
  min?: number;
  max?: number;
  step?: number;
  /** When true, an empty "(none)" option is allowed (server default null). */
  nullable?: boolean;
  group: 'key' | 'advanced';
  placeholder?: string;
  /** Schema description, rendered as helper text under the control. */
  description?: string;
}

export interface SectionDef {
  key: string;
  title: string;
  fields: FieldDef[];
}

export type JsonSchema = Record<string, unknown>;

/** Fields the schema alone can't express well — hand overrides by "section.key". */
const FIELD_OVERRIDES: Record<string, Partial<FieldDef>> = {
  'netconvert.osm_highway_types': { group: 'key' },
  'netconvert.default_speed_limit': { group: 'key' },
  'netconvert.default_junction_type': { group: 'key' },
  'netconvert.tl_type': { group: 'key' },
  'netconvert.proj_utm': { group: 'key' },
  'random_trips.end': { group: 'key' },
  'random_trips.period': { group: 'key' },
  'random_trips.vehicle_class': { group: 'key' },
  'random_trips.seed': { group: 'key' },
  'sumo.end': { group: 'key' },
  'sumo.step_length': { group: 'key' },
  'sumo.fcd_output_period': { group: 'key' },
  'sumo.default_max_speed': { group: 'key' },
  'trace_exporter.output_format': { group: 'key' },
  'trace_exporter.sampling_period': { group: 'key' },
  'trace_exporter.penetration_rate': { group: 'key' },
  'trace_exporter.boundary': { placeholder: '0,0,5000,5000' },
  'netconvert.remove_edges_by_type': { placeholder: 'footway,cycleway,path' },
};

const SECTION_TITLES: Record<string, string> = {
  netconvert: 'Netconvert',
  random_trips: 'Random Trips',
  sumo: 'SUMO Simulation',
  trace_exporter: 'Trace Exporter',
};

function resolveRef(schema: JsonSchema, defs: JsonSchema): JsonSchema {
  const ref = schema.$ref;
  if (typeof ref === 'string') {
    const name = ref.split('/').pop() ?? '';
    const target = defs[name];
    if (target && typeof target === 'object') {
      return { ...(target as JsonSchema), description: schema.description ?? (target as JsonSchema).description } as JsonSchema;
    }
  }
  return schema;
}

/** Split Optional[T] anyOf into [non-null branches, nullable]. */
function flattenAnyOf(schema: JsonSchema): { type: JsonSchema; nullable: boolean } {
  const anyOf = schema.anyOf;
  if (Array.isArray(anyOf)) {
    const nonNull = anyOf.filter(
      (s) => (s as JsonSchema).type !== 'null',
    ) as JsonSchema[];
    const nullable = nonNull.length !== anyOf.length;
    if (nonNull.length === 1) return { type: nonNull[0], nullable };
    return { type: nonNull[0] ?? {}, nullable };
  }
  return { type: schema, nullable: false };
}

function fieldFromSchema(
  section: string,
  key: string,
  prop: JsonSchema,
  defs: JsonSchema,
): FieldDef {
  const { type: raw, nullable } = flattenAnyOf(prop);
  const resolved = resolveRef(raw, defs);
  const base: FieldDef = {
    key,
    label: key,
    type: 'text',
    nullable,
    group: 'advanced',
    description: (prop.description as string | undefined) ?? undefined,
  };

  // Enum select (either inline or via $ref).
  if (Array.isArray(resolved.enum)) {
    base.type = 'select';
    base.options = resolved.enum as string[];
  } else if (resolved.type === 'boolean') {
    base.type = 'boolean';
  } else if (resolved.type === 'integer' || resolved.type === 'number') {
    base.type = 'number';
    if (typeof resolved.minimum === 'number') base.min = resolved.minimum;
    if (typeof resolved.maximum === 'number') base.max = resolved.maximum;
    base.step = resolved.type === 'integer' ? 1 : undefined;
  } else if (resolved.type === 'array') {
    // Only the highway-types list today — chip multiselect.
    base.type = 'multiselect';
    const items = resolveRef((resolved.items as JsonSchema) ?? {}, defs);
    if (Array.isArray(items.enum)) base.options = items.enum as string[];
  }

  return { ...base, ...FIELD_OVERRIDES[`${section}.${key}`] };
}

/** sections from ConversionRequest.model_json_schema(). */
export function buildSections(schema: JsonSchema): SectionDef[] {
  const defs = (schema.$defs as JsonSchema) ?? {};
  const props = (schema.properties as JsonSchema) ?? {};
  return Object.entries(props).map(([key, prop]) => {
    const section = resolveRef(prop as JsonSchema, defs);
    const fields = Object.entries(
      (section.properties as JsonSchema) ?? {},
    ).map(([fieldKey, fieldProp]) =>
      fieldFromSchema(key, fieldKey, fieldProp as JsonSchema, defs),
    );
    return {
      key,
      title: SECTION_TITLES[key] ?? key,
      fields,
    };
  });
}
