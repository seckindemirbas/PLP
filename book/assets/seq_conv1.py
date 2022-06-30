import matplotlib.pyplot as plt
import seaborn as sns

sns.set_theme(style="darkgrid")

xdat = [n for n in range(1, 17)]
adat = [1 / x for x in xdat]
bdat = [(-1) ** x for x in xdat]


fig, ax = plt.subplots(1, 2, figsize=(12, 4))

plt.subplots_adjust(hspace=2.0)
sns.scatterplot(x=xdat, y=adat, ax=ax[0])
ax[0].set(
    xlabel="$n$",
    ylabel="$a_n$",
    yticks=[0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2],
    xticks=[0, 2, 4, 6, 8, 10, 12, 14, 16],
)

sns.scatterplot(x=xdat, y=bdat, ax=ax[1])
ax[1].set(
    xlabel="$n$",
    ylabel="$b_n$",
    yticks=[-3, -2, -1, 0, 1, 2, 3],
    xticks=[0, 2, 4, 6, 8, 10, 12, 14, 16],
)

fig.savefig("seq_conv1.svg")
fig.savefig("seq_conv1.pdf")
