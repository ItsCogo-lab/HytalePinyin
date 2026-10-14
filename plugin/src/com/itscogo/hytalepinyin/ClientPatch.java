package com.itscogo.hytalepinyin;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Installs the client side of HytalePinyin: the fonts with the pinyin letters
 * Hytale's own fonts lack, and pinyin in the menus.
 *
 * A server plugin normally can't touch the player's computer. But in
 * singleplayer the server runs on the player's computer, from
 * <game>/Server/HytaleServer.jar, right next to the client in <game>/Client,
 * so the plugin can copy the files there itself. The client reads them when
 * it starts, so the player restarts Hytale once. On a dedicated server there
 * is no client next to the server and nothing is done.
 *
 * The files come from the JAR's /client-patch folder (made by
 * tools/bundle_client_patch.py):
 *
 *  - Font atlases (UI/Fonts/*.json/png, used by tooltips and the HUD): only
 *    replaced if the game still has the exact original we were built from
 *    (originals.tsv), so a game update with new fonts is left alone.
 *  - HytalePinyin-Small.ttf, a small font with only the pinyin letters, added
 *    as the last fallback of every font family in the menus' .xaml files
 *    (UI/DesignSystem/Fonts.xaml, the theme, and any screen that names its
 *    own fonts, like the loading screen). The game keeps its own .ttf files
 *    open while it runs, so we add a new font instead of changing them.
 *  - Language/zh-CN/client.lang (menu texts): each official text in
 *    client-labels.tsv is swapped for the one with pinyin, line by line, so
 *    texts a game update adds are kept.
 *
 * Every file we change is first copied to UI/Fonts/_hytalepinyin_backup (the
 * game's path without "UI/Fonts/"), and restore() copies them back. A game
 * update puts the original files back by itself; the next world opened with
 * the mod installs again.
 */
final class ClientPatch {

    /** Where the bundled files are inside the JAR. */
    private static final String RESOURCES = "/client-patch/";
    private static final String SMALL_FONT = "UI/Fonts/HytalePinyin-Small.ttf";
    private static final String CLIENT_LANG = "Language/zh-CN/client.lang";
    /** What we add at the end of each font family: the small font's family name. */
    private static final String FALLBACK = ", /Fonts/#HytalePinyin";
    /**
     * A list of fonts in a .xaml file ("/Fonts/#Nunito Sans, /Fonts/#Noto Sans SC"),
     * either as an attribute (FontFamily="..." or a Setter's Value="...") or
     * as the text of a <FontFamily> element. Group 2 or 4 is the list.
     */
    private static final Pattern FONT_LIST =
            Pattern.compile("(\")([^\"<>]*Fonts/#[^\"<>]*)\"|(>)([^<>]*Fonts/#[^<>]*)<");
    /** If this file exists the player ran /hanzi restore, and nothing is installed again until /hanzi install. */
    private static final String DISABLED = "disabled.txt";

    /** What happened to the client on this computer. */
    enum State {
        /** No client next to the server: a dedicated server. */
        NO_CLIENT,
        /** Everything was already installed. */
        INSTALLED,
        /** Files were changed just now: the client sees them after a restart. */
        CHANGED,
        /** Turned off with /hanzi restore. */
        DISABLED,
        /** Some files could not be written or are from a game version we don't know. */
        INCOMPLETE
    }

    /** The result of install() or restore(): the state, the files changed, and one line per problem. */
    record Result(State state, List<String> changed, List<String> problems) {
        Result(State state, List<String> problems) {
            this(state, List.of(), problems);
        }
    }

    /** Client/Data/Shared of the game, or null on a dedicated server. */
    private final Path shared;

    ClientPatch(Path serverJar) {
        Path candidate = serverJar.getParent().getParent().resolve("Client/Data/Shared");
        this.shared = Files.isDirectory(candidate.resolve("UI/Fonts")) ? candidate : null;
    }

    /** Where the client is, for the log. */
    String describe() {
        return shared == null ? "none next to the server" : shared.toString();
    }

    boolean hasClient() {
        return shared != null;
    }

    private Path backupDir() {
        return shared.resolve("UI/Fonts/_hytalepinyin_backup");
    }

    /** Where a game file's original is kept: UI/Fonts/x.json -> _hytalepinyin_backup/x.json. */
    private Path backupOf(String gamePath) {
        return backupDir().resolve(gamePath.startsWith("UI/Fonts/") ? gamePath.substring("UI/Fonts/".length()) : gamePath);
    }

    boolean disabled() {
        return shared != null && Files.exists(backupDir().resolve(DISABLED));
    }

    /** Copies everything in; each file on its own, so one locked file doesn't stop the rest. */
    Result install() throws IOException {
        if (shared == null) {
            return new Result(State.NO_CLIENT, List.of());
        }
        if (disabled()) {
            return new Result(State.DISABLED, List.of());
        }
        // Earlier versions of the client patch (named VividHanzi) kept the originals here
        Path old = shared.resolve("UI/Fonts/_vividhanzi_backup");
        if (Files.isDirectory(old) && !Files.exists(backupDir())) {
            Files.move(old, backupDir());
        }
        List<String> problems = new ArrayList<>();
        List<String> changed = new ArrayList<>();

        for (Map.Entry<String, String> atlas : originals().entrySet()) {
            String path = atlas.getKey();
            try {
                Path game = shared.resolve(path);
                byte[] ours = resource("files/" + path);
                String current = Files.exists(game) ? sha256(Files.readAllBytes(game)) : null;
                if (sha256(ours).equals(current)) {
                    continue;
                }
                if (!atlas.getValue().equals(current)) {
                    problems.add(path + " is not the file this version of HytalePinyin was made for (new game version?)");
                    continue;
                }
                backup(path);
                Files.write(game, ours);
                changed.add(path);
            } catch (IOException e) {
                problems.add(path + ": " + e);
            }
        }

        try {
            byte[] font = resource("files/" + SMALL_FONT);
            Path game = shared.resolve(SMALL_FONT);
            if (!Files.exists(game) || !sha256(Files.readAllBytes(game)).equals(sha256(font))) {
                Files.write(game, font);
                changed.add(SMALL_FONT);
            }
        } catch (IOException e) {
            problems.add(SMALL_FONT + ": " + e);
        }

        for (String path : xamlFiles()) {
            try {
                Path game = shared.resolve(path);
                String text = Files.readString(game, StandardCharsets.UTF_8);
                String patched = withFallback(text);
                if (patched.equals(text)) {
                    continue;
                }
                // Only a file with none of our fallbacks is an original worth keeping
                if (!text.contains(FALLBACK)) {
                    backup(path);
                }
                Files.writeString(game, patched, StandardCharsets.UTF_8);
                changed.add(path);
            } catch (IOException e) {
                problems.add(path + ": " + e);
            }
        }

        try {
            Path game = shared.resolve(CLIENT_LANG);
            if (Files.exists(game)) {
                String text = Files.readString(game, StandardCharsets.UTF_8);
                Map<String, String[]> labels = labels();
                Relabeled relabeled = relabel(text, labels, false);
                if (relabeled.count() > 0) {
                    // Only a file with none of our texts is an original worth keeping
                    if (relabel(text, labels, true).count() == 0) {
                        backup(CLIENT_LANG);
                    }
                    Files.writeString(game, relabeled.text(), StandardCharsets.UTF_8);
                    changed.add(CLIENT_LANG);
                }
            }
        } catch (IOException e) {
            problems.add(CLIENT_LANG + ": " + e);
        }

        State state = !problems.isEmpty() ? State.INCOMPLETE : !changed.isEmpty() ? State.CHANGED : State.INSTALLED;
        return new Result(state, changed, problems);
    }

    /**
     * Puts the game's own files back and turns the patch off, so the next
     * world doesn't install it again (until /hanzi install).
     */
    Result restore() throws IOException {
        if (shared == null) {
            return new Result(State.NO_CLIENT, List.of());
        }
        List<String> problems = new ArrayList<>();
        List<String> changed = new ArrayList<>();
        List<String> paths = new ArrayList<>(originals().keySet());
        paths.addAll(xamlFiles());
        paths.add(CLIENT_LANG);
        for (String path : paths) {
            try {
                // Only over our own version: after a game update the game's file is newer than the backup
                if (!isOurs(path)) {
                    continue;
                }
                Path backup = backupOf(path);
                if (Files.exists(backup)) {
                    Files.copy(backup, shared.resolve(path), StandardCopyOption.REPLACE_EXISTING);
                    changed.add(path);
                } else if (path.endsWith(".xaml")) {
                    // No copy (lost in a game update?): taking our fallback out gives the original
                    Path game = shared.resolve(path);
                    Files.writeString(game, Files.readString(game, StandardCharsets.UTF_8).replace(FALLBACK, ""),
                            StandardCharsets.UTF_8);
                    changed.add(path);
                }
            } catch (IOException e) {
                problems.add(path + ": " + e);
            }
        }
        try {
            Files.deleteIfExists(shared.resolve(SMALL_FONT));
        } catch (IOException e) {
            // Without the fallback in Fonts.xaml nothing reads it, so it can stay
            problems.add(SMALL_FONT + ": " + e);
        }
        Files.createDirectories(backupDir());
        Files.writeString(backupDir().resolve(DISABLED),
                "HytalePinyin's client patch was removed with /hanzi restore. /hanzi install puts it back.\n");
        return new Result(problems.isEmpty() ? State.DISABLED : State.INCOMPLETE, changed, problems);
    }

    /** Lets install() run again after a restore. */
    void enable() throws IOException {
        if (shared != null) {
            Files.deleteIfExists(backupDir().resolve(DISABLED));
        }
    }

    private boolean isOurs(String path) throws IOException {
        Path game = shared.resolve(path);
        if (!Files.exists(game)) {
            return false;
        }
        if (path.endsWith(".xaml")) {
            return Files.readString(game, StandardCharsets.UTF_8).contains(FALLBACK);
        }
        if (path.equals(CLIENT_LANG)) {
            return relabel(Files.readString(game, StandardCharsets.UTF_8), labels(), true).count() > 0;
        }
        return sha256(Files.readAllBytes(game)).equals(sha256(resource("files/" + path)));
    }

    /** Every .xaml file of the menus, as paths from Client/Data/Shared with "/". */
    private List<String> xamlFiles() throws IOException {
        Path ui = shared.resolve("UI");
        try (var files = Files.walk(ui)) {
            return files.filter(f -> f.toString().endsWith(".xaml") && !f.startsWith(backupDir()))
                    .map(f -> shared.relativize(f).toString().replace('\\', '/'))
                    .sorted().toList();
        }
    }

    /** The .xaml text with our small font at the end of every list of fonts that lacks it. */
    static String withFallback(String xaml) {
        Matcher m = FONT_LIST.matcher(xaml);
        StringBuilder out = new StringBuilder();
        while (m.find()) {
            boolean attribute = m.group(1) != null;
            String fonts = attribute ? m.group(2) : m.group(4);
            String patched = fonts.contains(FALLBACK) ? fonts : fonts.stripTrailing() + FALLBACK
                    + fonts.substring(fonts.stripTrailing().length());
            // appendReplacement treats "$" and "\" specially, hence quoteReplacement
            m.appendReplacement(out, Matcher.quoteReplacement(attribute ? "\"" + patched + "\"" : ">" + patched + "<"));
        }
        m.appendTail(out);
        return out.toString();
    }

    private void backup(String path) throws IOException {
        Path backup = backupOf(path);
        Files.createDirectories(backup.getParent());
        Files.copy(shared.resolve(path), backup, StandardCopyOption.REPLACE_EXISTING);
    }

    /** A .lang file with labels swapped, and how many were swapped. */
    private record Relabeled(String text, int count) {
    }

    /**
     * Swaps each label in client.lang from the official text to the one with
     * pinyin (or, with `reverse`, only counts the ones already with pinyin).
     *
     * Same rules as the game's parser: "key = value", # comments, a value
     * ending in "\" continues on the next line, quotes around a value are
     * dropped. An entry spread over several lines is written back as one.
     * The file's own line endings (CRLF on Windows) are kept.
     */
    private static Relabeled relabel(String text, Map<String, String[]> labels, boolean reverse) {
        String newline = text.contains("\r\n") ? "\r\n" : "\n";
        String[] lines = text.split("\r?\n", -1);
        StringBuilder out = new StringBuilder();
        int count = 0;
        boolean continued = false; // this line is the rest of the entry above
        for (int i = 0; i < lines.length; i++) {
            String line = lines[i].strip();
            int eq = line.indexOf('=');
            String[] label = continued || line.startsWith("#") || eq < 0 ? null : labels.get(line.substring(0, eq).strip());
            if (label == null) {
                if (!line.startsWith("#") && (continued || eq >= 0)) {
                    continued = line.endsWith("\\");
                }
                out.append(lines[i]).append(i + 1 < lines.length ? newline : "");
                continue;
            }
            // Join the continuation lines of this entry
            int last = i;
            StringBuilder value = new StringBuilder();
            String part = line.substring(eq + 1).strip();
            while (part.endsWith("\\") && last + 1 < lines.length) {
                value.append(part, 0, part.length() - 1);
                part = lines[++last].strip();
                if (part.startsWith("#")) {
                    part = "";
                }
            }
            value.append(part.endsWith("\\") ? part.substring(0, part.length() - 1) : part);
            String v = value.toString();
            if (v.length() > 1 && v.startsWith("\"") && v.endsWith("\"")) {
                v = v.substring(1, v.length() - 1);
            }
            if (reverse ? v.equals(label[1]) : v.equals(label[0])) {
                count++;
                if (!reverse) {
                    out.append(line, 0, eq).append("= ").append(label[1]).append(last + 1 < lines.length ? newline : "");
                    i = last;
                    continue;
                }
            }
            for (int j = i; j <= last; j++) {
                out.append(lines[j]).append(j + 1 < lines.length ? newline : "");
            }
            i = last;
        }
        return new Relabeled(out.toString(), count);
    }

    /** client-labels.tsv: key -> {official text, text with pinyin}. */
    private static Map<String, String[]> labels() throws IOException {
        Map<String, String[]> labels = new LinkedHashMap<>();
        for (String[] row : tsv("client-labels.tsv")) {
            labels.put(row[0], new String[] {row[1], row[2]});
        }
        return labels;
    }

    /** originals.tsv: atlas path -> SHA-256 of the game's original. */
    private static Map<String, String> originals() throws IOException {
        Map<String, String> originals = new LinkedHashMap<>();
        for (String[] row : tsv("originals.tsv")) {
            originals.put(row[0], row[1]);
        }
        return originals;
    }

    /** The rows of a bundled .tsv file, without its header. */
    private static List<String[]> tsv(String name) throws IOException {
        List<String[]> rows = new ArrayList<>();
        String[] lines = new String(resource(name), StandardCharsets.UTF_8).split("\n");
        for (int i = 1; i < lines.length; i++) {
            if (!lines[i].isEmpty()) {
                rows.add(lines[i].split("\t", -1));
            }
        }
        return rows;
    }

    private static byte[] resource(String name) throws IOException {
        try (InputStream in = ClientPatch.class.getResourceAsStream(RESOURCES + name)) {
            if (in == null) {
                throw new IOException("missing resource " + RESOURCES + name);
            }
            return in.readAllBytes();
        }
    }

    private static String sha256(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IllegalStateException(e); // every Java has SHA-256
        }
    }
}
