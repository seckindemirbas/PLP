/**
 * <h2>Notes on use with the CodeChat System</h2>
 *
 * <p>Compared to a standard Javadoc setup, the CodeChat project configuration file (named <code>codechat_config.yaml</code>) invokes <code>javadoc</code> with the <code>-d _build</code> option; matching this, the configuration file specifies the output directory <code>_build</code>.
 *
 * To use these files, simply copy them to a new project directory of your choice. Open them in your preferred text editor/IDE, then use a appropriate CodeChat extension/plugin to open any of these files to build and view the results.
 */
public class Simple{
    /**
     * Write the actual message.
     *
     * @param args The command-line arguments, which are ignored.
     */
    public static void main(String args[]) {
        System.out.println("Hello Java");
    }
}
