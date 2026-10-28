library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity i2s_transmitter is
    port (
        bclk      : in  std_logic;   -- Bit Clock (3.072 MHz)
        lrclk     : in  std_logic;   -- Word Select (48 kHz, wechselt bei falling_edge von bclk)
        rst       : in  std_logic;   -- Active-low Reset
        data_left : in  signed(15 downto 0);
        data_right: in  signed(15 downto 0);
        sdata     : out std_logic
    );
end entity;

architecture rtl of i2s_transmitter is
    signal shift_reg : std_logic_vector(31 downto 0) := (others => '0');
    signal lrclk_d   : std_logic := '0';
    signal sdata_i   : std_logic := '0';
begin

    sdata <= sdata_i;

    process(bclk, rst)
    begin
        if rst = '0' then
            shift_reg <= (others => '0');
            lrclk_d   <= '0';
            sdata_i   <= '0';
        elsif falling_edge(bclk) then
            lrclk_d <= lrclk;
            if lrclk_d /= lrclk then
                if lrclk = '0' then
                    sdata_i   <= data_left(15); -- MSB (Vorzeichen) direkt ausgeben
                    shift_reg <= std_logic_vector(data_left(14 downto 0)) & x"0000" & '0';
                else
                    sdata_i   <= data_right(15); -- MSB (Vorzeichen) direkt ausgeben
                    shift_reg <= std_logic_vector(data_right(14 downto 0)) & x"0000" & '0';
                end if;
            else
                -- Nächstes Bit bei fallender Flanke ausgeben
                sdata_i   <= shift_reg(31);
                shift_reg <= shift_reg(30 downto 0) & '0';
            end if;
        end if;
    end process;

end architecture;
