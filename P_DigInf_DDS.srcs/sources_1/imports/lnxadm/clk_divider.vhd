-- clk_divider.vhd
-- Erzeugt aus 24.576 MHz:
--   - BCLK   = 3.072 MHz   (MCLK/8)
--   - LRCLK  = 48 kHz      (BCLK/64 = MCLK/512)

library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity clk_divider is
    port (
        clk_24_576m  : in  std_logic;   -- 24.576 MHz Master Clock
        rst          : in  std_logic;
        
        bclk         : out std_logic;   -- 3.072 MHz
        lrclk        : out std_logic    -- 48 kHz
    );
end entity clk_divider;

architecture rtl of clk_divider is

    signal bclk_cnt  : unsigned(2 downto 0) := (others => '0');   -- /8 (Halbperiode: 4 MCLKs)
    signal lrclk_cnt : unsigned(5 downto 0) := (others => '0');   -- /64 BCLKs (Halbperiode: 32 BCLKs)

    signal bclk_i    : std_logic := '0';
    signal lrclk_i   : std_logic := '0';

begin

    process(clk_24_576m)
    begin
        if rising_edge(clk_24_576m) then
            if rst = '0' then
                bclk_cnt  <= (others => '0');
                lrclk_cnt <= (others => '0');
                bclk_i    <= '0';
                lrclk_i   <= '0';
            else
                -- BCLK Teiler (alle 4 MCLK-Takte umschalten)
                if bclk_cnt = 3 then
                    bclk_cnt <= (others => '0');
                    bclk_i   <= not bclk_i;
                    
                    -- LRCLK synchron weiterzählen, wenn BCLK von HIGH auf LOW wechselt
                    if bclk_i = '1' then
                        if lrclk_cnt = 31 then
                            lrclk_cnt <= (others => '0');
                            lrclk_i   <= not lrclk_i;
                        else
                            lrclk_cnt <= lrclk_cnt + 1;
                        end if;
                    end if;
                else
                    bclk_cnt <= bclk_cnt + 1;
                end if;
            end if;
        end if;
    end process;

    bclk  <= bclk_i;
    lrclk <= lrclk_i;

end architecture rtl;