#!/usr/bin/perl
# Prefixa cada linha de stdin com HH:MM:SS.mmm (relogio local). Usado para dar
# timestamp a `kubectl get ... -w`, que nao imprime hora nenhuma.
use strict;
use warnings;
use POSIX qw(strftime);
use Time::HiRes qw(time);
$| = 1;
while (my $linha = <STDIN>) {
    my $t = time;
    printf "[%s.%03d] %s", strftime("%H:%M:%S", localtime($t)), ($t - int($t)) * 1000, $linha;
}
