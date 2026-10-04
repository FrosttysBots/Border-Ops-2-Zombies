// Read-only T6 Zombies probe. Requires Plutonium's sandboxed fs_* builtins.
// Do not load on public servers. No gameplay replacement or remote commands.
init()
{
    level thread blacklands_probe();
}

blacklands_probe()
{
    level endon("game_ended");
    sequence = 0;
    last_reply = "";
    print("[BlackLands] BO2 probe loaded; waiting for one local player.\n");
    for (;;)
    {
        players = getentarray("player", "classname");
        if (players.size == 1 && isdefined(players[0].origin) && isdefined(players[0].health))
        {
            player = players[0];
            p = player.origin;
            a = player getplayerangles();
            weapon = player getcurrentweapon();
            if (!isdefined(weapon) || weapon == "")
                weapon = "none";
            round = 0;
            if (isdefined(level.round_number))
                round = level.round_number;
            health = player.health;
            if (health < 0)
                health = 0;
            frame = "BLPT1|" + sequence + "|" + gettime() + "|" + p[0] + "|" + p[1] + "|" + p[2] + "|" + a[0] + "|" + a[1] + "|" + a[2] + "|" + health + "|" + round + "|" + weapon + "|END";
            file = fs_fopen("blacklands_host.txt", "write");
            if (file > 0)
            {
                fs_writeline(file, frame);
                fs_fclose(file);
            }
            if (fs_testfile("blacklands_reply.txt"))
            {
                file = fs_fopen("blacklands_reply.txt", "read");
                if (file > 0)
                {
                    reply = fs_readline(file);
                    fs_fclose(file);
                    if (isdefined(reply) && reply != last_reply)
                    {
                        // Console acknowledgement only; never evaluate incoming text.
                        print("[BlackLands] donor reply: " + reply + "\n");
                        last_reply = reply;
                    }
                }
            }
            sequence++;
            if (sequence > 2000000000)
                sequence = 0;
        }
        wait 0.25;
    }
}
