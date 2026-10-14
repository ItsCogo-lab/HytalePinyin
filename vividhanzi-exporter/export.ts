/*
 * "hytale" exporter: annotates a list of Chinese texts with the app's own
 * pinyin pipeline and writes one compact JSON with everything an offline
 * consumer needs (made for HytalePinyin, a Hytale mod, which can't make
 * network requests in game).
 *
 *   node scripts/hytale/export.ts --texts texts.json --dictionary ../HanziDict/v1 --out hytale.json
 *                                 [--extra-words extra-words.json] [--frequencies frequencies.json]
 *
 * - texts.json: a JSON array of strings (item names, sentences...).
 * - --dictionary: a local copy of the data repository's v1 folder
 *   (ItsCogo-lab/HanziDict), so the export needs no network either.
 * - --extra-words: optional JSON array of { hanzi, pinyin, en? } for terms the
 *   dictionary doesn't have (a game's own compounds, 水蓝石 "aqua stone").
 *   They take part in segmentation and readings like dictionary words.
 * - --frequencies: optional JSON object word → frequency (0-1, e.g. from
 *   wordfreq). With it, texts are split into their most likely words instead
 *   of by longest match: 在地图上 is 在 · 地图 · 上, not 在地 · 图 · 上.
 *
 * Each text goes through the same steps as an example sentence in the app
 * (ExampleSentences.tsx): pinyin-pro reading with 一/不 tone sandhi, split into
 * dictionary words (by longest match, or by frequency with --frequencies), readings filled in from the dictionary
 * and grammar rules, and a second split with those readings to pick homographs.
 *
 * Output:
 *   texts:      text → its words, [hanzi, pinyin] or [hanzi, pinyin, "?"] when a
 *               syllable is uncertain, or [text] for punctuation and other symbols.
 *   words:      hanzi → its dictionary entries (homographs too), for every word
 *               used in a text and every HSK 1-4 word.
 *   characters: hanzi → its entry, for every character used and every HSK 1-4 character.
 */
import { readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { parseArgs } from 'node:util'
import { annotateSentence } from '../../src/features/customSets/pinyinEngine.ts'
import { getDatasetReadings } from '../../src/features/customSets/sentenceProcessing.ts'
import type { SentenceToken } from '../../src/features/customSets/types.ts'
import { createDictionaryStore } from '../../src/features/dictionary/dictionaryStore.ts'
import { getChunkIndex, type DictionaryChunk } from '../../src/features/dictionary/fullDictionary.ts'
import { hskDictionary } from '../../src/features/dictionary/hskDictionary.ts'
import { segmentSentence, type SentenceWord, type WordIndex } from '../../src/features/dictionary/segmentation.ts'
import { resolveReadings } from '../../src/features/dictionary/sentenceReadings.ts'
import type { Character, Word } from '../../src/features/dictionary/types.ts'

/** Bump when the output's shape changes, so consumers can check it. */
const EXPORT_FORMAT = 1
const HAN = /\p{Script=Han}/u

interface ExtraWord {
  hanzi: string
  pinyin: string
  en?: string
}

/** A text's word: [hanzi, pinyin], [hanzi, pinyin, "?"] if uncertain, or [symbols]. */
type ExportedWord = [string] | [string, string] | [string, string, '?']

const { values: args } = parseArgs({
  options: {
    texts: { type: 'string' },
    dictionary: { type: 'string' },
    'extra-words': { type: 'string' },
    frequencies: { type: 'string' },
    out: { type: 'string' },
  },
})
if (!args.texts || !args.dictionary || !args.out) {
  console.error('Usage: export.ts --texts texts.json --dictionary HanziDict/v1 --out out.json [--extra-words words.json] [--frequencies frequencies.json]')
  process.exit(1)
}

const readJson = async (path: string): Promise<unknown> => JSON.parse(await readFile(path, 'utf8'))
const texts = (await readJson(args.texts)) as string[]
const manifest = (await readJson(join(args.dictionary, 'manifest.json'))) as { version: string; sources: object }
const extraWords = args['extra-words'] ? ((await readJson(args['extra-words'])) as ExtraWord[]) : []
const frequencies = args.frequencies ? ((await readJson(args.frequencies)) as Record<string, number>) : undefined
const extraHanzi = new Set(extraWords.map((extra) => extra.hanzi))
// A dictionary word the frequency list doesn't have (it comes from a
// segmenter that never produced that word: 死区, 槽位) is estimated as the
// product of its characters' frequencies times WORD_BONUS per extra
// character, so it beats its own characters one by one but not a split into
// words the list does know (在地 · 图 loses to 在 · 地图). An extra word is the
// game's own term and should always win. A character that isn't in the
// dictionary at all is the last resort.
const WORD_BONUS = 100
const MISSING_CHARACTER = 1e-7
const EXTRA_WORD = 1e-4
const NOT_A_WORD = 1e-12

function frequencyOf(hanzi: string, list: Record<string, number>): number {
  if (extraHanzi.has(hanzi)) return EXTRA_WORD
  if (list[hanzi] !== undefined) return list[hanzi]
  const characters = Array.from(hanzi)
  return characters.reduce((product, character) => product * (list[character] ?? MISSING_CHARACTER), 1) *
    WORD_BONUS ** (characters.length - 1)
}

// The extra words go in the chunk of their first character, like any other word
const extraByChunk = new Map<number, ExtraWord[]>()
for (const extra of extraWords) {
  const chunk = getChunkIndex(extra.hanzi)
  extraByChunk.set(chunk, [...(extraByChunk.get(chunk) ?? []), extra])
}
const store = createDictionaryStore(hskDictionary, async (index) => {
  const path = join(args.dictionary!, manifest.version, 'dictionary', `${index}.json`)
  const chunk = (await readJson(path)) as DictionaryChunk
  const ids = new Set([...chunk.words.map((word) => word.id), ...hskDictionary.words.keys()])
  const extras = (extraByChunk.get(index) ?? []).map(
    (extra): Word => ({
      // Same id convention as homographs if the dictionary already has that hanzi
      id: ids.has(extra.hanzi) ? `${extra.hanzi}[${extra.pinyin}]` : extra.hanzi,
      hanzi: extra.hanzi,
      pinyin: extra.pinyin,
      meanings: { en: extra.en ? [extra.en] : [] },
    }),
  )
  return { characters: chunk.characters, words: [...chunk.words, ...extras] }
})
await store.loadAll()

const exported: Record<string, ExportedWord[]> = {}
const usedWords = new Set<string>()
const usedCharacters = new Set<string>()
for (const text of new Set(texts)) {
  exported[text] = annotate(text, store.wordIndex)
  for (const [hanzi, pinyin] of exported[text]) {
    if (pinyin === undefined) continue
    usedWords.add(hanzi)
    for (const character of hanzi) usedCharacters.add(character)
  }
}

// Every HSK 1-4 entry too, so the consumer can show levels and browse them
const dictionary = store.getSnapshot()
const words: Record<string, ReturnType<typeof compactWord>[]> = {}
for (const word of dictionary.words.values()) {
  if (word.hskLevel !== undefined || usedWords.has(word.hanzi)) {
    ;(words[word.hanzi] ??= []).push(compactWord(word))
  }
}
const characters: Record<string, ReturnType<typeof compactCharacter>> = {}
for (const character of dictionary.characters.values()) {
  if (character.hskLevel !== undefined || usedCharacters.has(character.hanzi)) {
    characters[character.hanzi] = compactCharacter(character)
  }
}

await writeFile(
  args.out,
  JSON.stringify({
    format: EXPORT_FORMAT,
    generatedAt: new Date().toISOString(),
    dictionaryVersion: manifest.version,
    sources: {
      ...manifest.sources,
      readings: 'pinyin-pro (MIT) with CC-CEDICT, as in the VividHanzi app',
      hsk: 'clem109/hsk-vocabulary (MIT), HSK 2.0 levels 1-4',
    },
    licenses: 'CC-CEDICT CC BY-SA 4.0; Unihan Unicode License v3; Make Me a Hanzi LGPL 3.0+; hanzi-writer-data Arphic Public License; wordfreq CC BY-SA 4.0',
    texts: exported,
    words,
    characters,
  }),
)
console.log(
  `${Object.keys(exported).length} texts, ${Object.keys(words).length} words, ${Object.keys(characters).length} characters → ${args.out}`,
)

/** The app's pipeline for one text (see ExampleSentences.tsx), grouped into words. */
function annotate(text: string, index: WordIndex): ExportedWord[] {
  let tokens = annotateSentence(text, getDatasetReadings)
  tokens = resolveReadings(tokens, segment(text, index, readingsOf(tokens)), index)
  const pieces = segment(text, index, readingsOf(tokens))

  // One reading per character, and whether it's uncertain
  const perCharacter = tokens.flatMap((token) =>
    Array.from(token.text, () => ({ pinyin: token.pinyin, uncertain: token.uncertain === true })),
  )
  const result: ExportedWord[] = []
  let offset = 0
  for (const piece of pieces) {
    const length = Array.from(piece.text).length
    const readings = perCharacter.slice(offset, offset + length)
    offset += length
    if (!piece.item || !HAN.test(piece.text)) {
      result.push([piece.text])
      continue
    }
    const pinyin = readings.map((reading) => reading.pinyin ?? '?').join(' ')
    result.push(readings.some((reading) => reading.uncertain) ? [piece.text, pinyin, '?'] : [piece.text, pinyin])
  }
  return result
}

/**
 * Splits a text into the sequence of dictionary words with the highest
 * probability (the product of their frequencies, as most Chinese segmenters
 * do), then lets segmentSentence pick each word's entry. Without
 * --frequencies it's the app's longest match.
 */
function segment(text: string, index: WordIndex, readings: readonly (string | undefined)[]): SentenceWord[] {
  if (!frequencies) return segmentSentence(text, index, readings)
  const symbols = Array.from(text)
  // cost[i]: lowest -log(probability) to split the first i symbols; from[i]: where its last piece starts
  const cost = [0, ...symbols.map(() => Infinity)]
  const from = symbols.map(() => 0)
  const relax = (start: number, end: number, frequency: number) => {
    const total = cost[start]! - Math.log(frequency)
    if (total < cost[end]!) {
      cost[end] = total
      from[end - 1] = start
    }
  }
  for (let start = 0; start < symbols.length; start++) {
    if (!HAN.test(symbols[start]!)) {
      relax(start, start + 1, 1) // punctuation and letters cost nothing
      continue
    }
    relax(start, start + 1, NOT_A_WORD)
    for (let length = 1; length <= Math.min(index.longest(), symbols.length - start); length++) {
      const hanzi = symbols.slice(start, start + length).join('')
      if (index.find(hanzi).length === 0) continue
      relax(start, start + length, frequencyOf(hanzi, frequencies))
    }
  }
  const bounds: number[] = []
  for (let end = symbols.length; end > 0; end = from[end - 1]!) bounds.unshift(end)
  // Each piece is a whole dictionary word (or one symbol), so segmentSentence
  // returns it as one word with the entry that matches its reading
  const words: SentenceWord[] = []
  let start = 0
  for (const end of bounds) {
    for (const word of segmentSentence(symbols.slice(start, end).join(''), index, readings.slice(start, end))) {
      const last = words.at(-1)
      if (!word.item && last && !last.item) last.text += word.text
      else words.push(word)
    }
    start = end
  }
  return words
}

/** Each character's reading, undefined where uncertain (picks among homographs). */
function readingsOf(tokens: readonly SentenceToken[]): (string | undefined)[] {
  return tokens.flatMap((token) => Array.from(token.text, () => (token.uncertain ? undefined : token.pinyin)))
}

/** A word without the fields an offline consumer doesn't need (id, frequency rank). */
function compactWord(word: Word) {
  return {
    pinyin: word.pinyin,
    en: word.meanings.en,
    ...(word.hskLevel !== undefined && { hsk: word.hskLevel }),
    ...(word.traditional !== undefined && word.traditional !== word.hanzi && { traditional: word.traditional }),
  }
}

function compactCharacter(character: Character) {
  return {
    pinyin: character.pinyin,
    en: character.meanings.en,
    ...(character.hskLevel !== undefined && { hsk: character.hskLevel }),
    ...(character.radical !== undefined && { radical: character.radical }),
    ...(character.strokeCount !== undefined && { strokes: character.strokeCount }),
    ...(character.decomposition !== undefined && { decomposition: character.decomposition }),
    ...(character.etymology !== undefined && { etymology: character.etymology }),
    ...(character.traditional !== undefined && { traditional: character.traditional }),
  }
}
