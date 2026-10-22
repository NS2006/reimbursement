/** The texts of one language for a namespace: the same keys as the English ones (locales/en), each a string. A
 * translation that misses a key, or has one English does not, does not build. */
export type Translation<T> = { [K in keyof T]: T[K] extends string ? string : Translation<T[K]> };
