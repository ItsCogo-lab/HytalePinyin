package com.itscogo.hytalepinyin;

import com.hypixel.hytale.component.Ref;
import com.hypixel.hytale.component.Store;
import com.hypixel.hytale.server.core.Message;
import com.hypixel.hytale.server.core.command.system.CommandContext;
import com.hypixel.hytale.server.core.command.system.basecommands.AbstractPlayerCommand;
import com.hypixel.hytale.server.core.universe.PlayerRef;
import com.hypixel.hytale.server.core.universe.world.World;
import com.hypixel.hytale.server.core.universe.world.storage.EntityStore;

import java.util.function.UnaryOperator;

/**
 * /hanzi shows your settings; /hanzi colors and /hanzi english switch them.
 * Settings are per player: nobody else's tooltips change.
 * /hanzi restore and /hanzi install remove and put back the fonts and menus
 * with pinyin in the Hytale client on this computer (singleplayer only).
 */
public class HanziCommand extends AbstractPlayerCommand {

    private final HytalePinyinPlugin plugin;

    public HanziCommand(HytalePinyinPlugin plugin) {
        super("hanzi", "HytalePinyin settings: /hanzi colors, /hanzi english");
        this.plugin = plugin;
        // Each subcommand flips one setting. UnaryOperator is "a function from
        // Settings to Settings", written here as a lambda.
        addSubCommand(new Toggle(plugin, "colors", "Tone colours in the pinyin on/off",
                s -> new HytalePinyinPlugin.Settings(!s.tones(), s.english())));
        addSubCommand(new Toggle(plugin, "english", "English name and description on/off",
                s -> new HytalePinyinPlugin.Settings(s.tones(), !s.english())));
        addSubCommand(new Client(plugin, "restore", "Put back Hytale's original fonts and menus", true));
        addSubCommand(new Client(plugin, "install", "Install the fonts and menus with pinyin again", false));
    }

    @Override
    protected void execute(CommandContext context, Store<EntityStore> store, Ref<EntityStore> ref,
                           PlayerRef player, World world) {
        player.sendMessage(Message.raw(status(plugin.settingsOf(player)) + "  (/hanzi colors, /hanzi english)"));
    }

    static String status(HytalePinyinPlugin.Settings s) {
        return "HytalePinyin: tone colours " + (s.tones() ? "ON" : "OFF") + ", English " + (s.english() ? "ON" : "OFF");
    }

    /** A subcommand that changes the player's settings with `change`. */
    private static class Toggle extends AbstractPlayerCommand {
        private final HytalePinyinPlugin plugin;
        private final UnaryOperator<HytalePinyinPlugin.Settings> change;

        Toggle(HytalePinyinPlugin plugin, String name, String description,
               UnaryOperator<HytalePinyinPlugin.Settings> change) {
            super(name, description);
            this.plugin = plugin;
            this.change = change;
        }

        @Override
        protected void execute(CommandContext context, Store<EntityStore> store, Ref<EntityStore> ref,
                               PlayerRef player, World world) {
            HytalePinyinPlugin.Settings updated = change.apply(plugin.settingsOf(player));
            plugin.change(player, updated);
            String note = HytalePinyinPlugin.LANGUAGE.equals(player.getLanguage()) ? ""
                    : " (only applies with the game in Simplified Chinese)";
            player.sendMessage(Message.raw(status(updated) + note));
        }
    }

    /** /hanzi restore and /hanzi install: the client patch on this computer (see ClientPatch). */
    private static class Client extends AbstractPlayerCommand {
        private final HytalePinyinPlugin plugin;
        private final boolean restore;

        Client(HytalePinyinPlugin plugin, String name, String description, boolean restore) {
            super(name, description);
            this.plugin = plugin;
            this.restore = restore;
        }

        @Override
        protected void execute(CommandContext context, Store<EntityStore> store, Ref<EntityStore> ref,
                               PlayerRef player, World world) {
            ClientPatch patch = plugin.clientPatch();
            if (patch == null || !patch.hasClient()) {
                player.sendMessage(Message.raw("HytalePinyin: this server has no Hytale client next to it. "
                        + "Run this in a singleplayer world on your own computer."));
                return;
            }
            ClientPatch.Result result;
            try {
                if (!restore) {
                    patch.enable();
                }
                result = restore ? patch.restore() : patch.install();
            } catch (Exception e) {
                result = new ClientPatch.Result(ClientPatch.State.INCOMPLETE, java.util.List.of(e.toString()));
            }
            plugin.logClientPatch(restore ? "/hanzi restore" : "/hanzi install", result);
            String text = switch (result.state()) {
                case DISABLED -> "HytalePinyin: Hytale's original fonts and menus are back. Restart Hytale to "
                        + "see them. Worlds won't install the pinyin fonts again until /hanzi install.";
                case CHANGED -> "HytalePinyin: installed the fonts and menus with pinyin. Restart Hytale once "
                        + "to see them.";
                case INSTALLED -> "HytalePinyin: the fonts and menus with pinyin were already installed.";
                default -> "HytalePinyin: some files could not be changed (see the log). Close other programs "
                        + "using Hytale's files and try again.";
            };
            player.sendMessage(Message.raw(text));
        }
    }
}
