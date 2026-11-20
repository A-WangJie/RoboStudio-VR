export class StudioError extends Error {
  constructor(code, message, cause) {
    super(message, cause === undefined ? undefined : { cause });
    this.name = 'StudioError';
    this.code = code;
  }
}

export async function during(code, message, action) {
  try {
    return await action();
  } catch (cause) {
    if (cause instanceof StudioError) throw cause;
    throw new StudioError(code, message, cause);
  }
}
